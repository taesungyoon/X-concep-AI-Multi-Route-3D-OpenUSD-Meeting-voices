"""Run with Omniverse Kit Python to convert GLB/FBX/OBJ into OpenUSD."""
from __future__ import annotations

import argparse
import asyncio

import omni.kit.asset_converter


async def convert(source: str, target: str) -> None:
    converter = omni.kit.asset_converter.get_instance()
    context = omni.kit.asset_converter.AssetConverterContext()
    context.ignore_materials = False
    context.ignore_animations = False
    context.merge_all_meshes = False
    task = converter.create_converter_task(source, target, None, context)
    success = await task.wait_until_finished()
    if not success:
        raise RuntimeError(task.get_error_message())
    print(target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    args = parser.parse_args()
    asyncio.get_event_loop().run_until_complete(convert(args.source, args.target))


if __name__ == "__main__":
    main()
