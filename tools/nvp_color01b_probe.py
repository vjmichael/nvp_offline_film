"""COLOR-01B: inspect precisely pinned OCIO 2.5/ACES 2 spaces and views."""
import json
import PyOpenColorIO as ocio

CONFIG_NAME="cg-config-v4.0.0_aces-v2.0_ocio-v2.5"
cfg=ocio.Config.CreateFromBuiltinConfig(CONFIG_NAME)
spaces=[space.getName() for space in cfg.getColorSpaces()]
displays=list(cfg.getDisplays())
report={
    "library_version":ocio.GetVersion(),
    "config_name":CONFIG_NAME,
    "config_cache_id":cfg.getCacheID(),
    "spaces":spaces,
    "displays":{name:list(cfg.getViews(name)) for name in displays},
    "role_scene_linear":(cfg.getColorSpace("scene_linear").getName()
        if cfg.getColorSpace("scene_linear") else None),
}
print(json.dumps(report, indent=2, sort_keys=True))
