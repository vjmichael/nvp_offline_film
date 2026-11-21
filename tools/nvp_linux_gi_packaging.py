"""Native build and frozen-runtime checks for the Debian GTK/WebKit boundary."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

NAMESPACES = {'GLib': '2.0', 'GObject': '2.0', 'Gio': '2.0', 'Gdk': '3.0',
              'Gtk': '3.0', 'WebKit2': '4.1', 'Soup': '3.0'}
OVERRIDES = tuple('gi.overrides.' + name for name in
                  ('GLib', 'GObject', 'Gio', 'Gdk', 'Gtk', 'GdkPixbuf', 'Pango'))


def exercise_gi():
    import gi
    for namespace, version in NAMESPACES.items():
        gi.require_version(namespace, version)
    for namespace in NAMESPACES:
        importlib.import_module('gi.repository.' + namespace)
    from gi.repository import GLib
    if any(name not in sys.modules for name in OVERRIDES):
        raise RuntimeError('Required GI overrides were not activated')
    loop = GLib.MainLoop()
    observed = []
    def callback():
        observed.append('idle')
        loop.quit()
        return False
    def expired():
        loop.quit()
        return False
    timeout = GLib.timeout_add(2000, expired)
    GLib.idle_add(callback)
    loop.run()
    if observed != ['idle']:
        raise RuntimeError('GLib callback dispatch failed')
    GLib.source_remove(timeout)


def build_inventory():
    if getattr(sys, 'frozen', False):
        raise RuntimeError('Build inventory requires native build Python')
    exercise_gi()
    import gi
    # Debian 13 pins PyGObject 3.50 and girepository-1.0 (GIRepository 2.0).
    gi.require_version('GIRepository', '2.0')
    from gi.repository import GIRepository
    repository = GIRepository.Repository.get_default()
    closure = dict(NAMESPACES)
    for namespace in NAMESPACES:
        for dependency in repository.get_dependencies(namespace):
            ns, version = dependency.rsplit('-', 1)
            if ns in closure and closure[ns] != version:
                raise RuntimeError('Conflicting typelib version: ' + ns)
            closure[ns] = version
    typelibs = []
    for namespace, version in sorted(closure.items()):
        repository.require(namespace, version, GIRepository.RepositoryLoadFlags.IREPOSITORY_LOAD_FLAG_LAZY)
        path = Path(repository.get_typelib_path(namespace)).resolve(strict=True)
        if not path.is_file() or path.name != f'{namespace}-{version}.typelib':
            raise RuntimeError('Missing exact typelib: ' + namespace)
        typelibs.append(str(path))
    return {'typelibs': typelibs, 'overrides': list(OVERRIDES)}


def verify_bundle(executable: Path, inventory):
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(executable))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    missing = set(OVERRIDES).difference(pyz.toc)
    if missing:
        raise RuntimeError('Frozen GI overrides missing: ' + ', '.join(sorted(missing)))
    for source in inventory['typelibs']:
        original = Path(source)
        target = executable.parent / '_internal' / 'gi_typelibs' / original.name
        if not target.is_file() or target.read_bytes() != original.read_bytes():
            raise RuntimeError('Frozen typelib missing or different: ' + original.name)
    return {'overrides': sorted(OVERRIDES), 'typelibs': sorted(Path(x).name for x in inventory['typelibs'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('inventory', 'flags', 'verify'))
    parser.add_argument('inventory', type=Path)
    parser.add_argument('executable', type=Path, nargs='?')
    args = parser.parse_args()
    if args.mode == 'inventory':
        args.inventory.write_text(json.dumps(build_inventory(), indent=2) + '\n')
    else:
        inventory = json.loads(args.inventory.read_text())
        if args.mode == 'flags':
            for module in OVERRIDES:
                print('--hidden-import=' + module)
            for source in inventory['typelibs']:
                print('--add-data=' + source + ':gi_typelibs')
        else:
            print(json.dumps(verify_bundle(args.executable, inventory), indent=2))


if __name__ == '__main__':
    main()
