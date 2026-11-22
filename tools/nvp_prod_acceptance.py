"""Run real PROD-01 or PROD-03 Blender acceptance against an approved NVP scene.

Examples:
  python -m tools.nvp_prod_acceptance --db ./movie.sqlite3 --project PX --scene SC --out ./acceptance
  python -m tools.nvp_prod_acceptance --db ./movie.sqlite3 --project PX --scene SC --out ./acceptance --meshpack
  python -m tools.nvp_prod_acceptance --db movie.sqlite3 --project PX --scene SC --out out --blender 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
"""
import argparse
import json
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_mesh_assets import MeshAssets
from backend.nvp_blender_acceptance import run_acceptance,run_meshpack_acceptance


def main(argv=None):
    parser=argparse.ArgumentParser(description='NVP production acceptance using real Blender')
    parser.add_argument('--db',required=True,help='NVP SQLite project DB')
    parser.add_argument('--project',required=True,help='Persisted NVP project id')
    parser.add_argument('--scene',required=True,help='Persisted screenplay scene id')
    parser.add_argument('--out',required=True,help='Output directory')
    parser.add_argument('--blender',default='blender',help='Blender executable or absolute path')
    parser.add_argument('--meshpack',action='store_true',help='Include registered GLB assets')
    args=parser.parse_args(argv)
    studio=Studio(Path(args.db))
    if args.meshpack:
        result=run_meshpack_acceptance(MeshAssets(studio),args.project,args.scene,
                                       args.out,executable=args.blender)
    else:
        result=run_acceptance(ProductionScene(studio),args.project,args.scene,
                              args.out,executable=args.blender)
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed_blender' else 2 if result['status']=='blocked_no_blender' else 1


if __name__=='__main__':raise SystemExit(main())
