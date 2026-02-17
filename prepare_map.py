#!/usr/bin/env python3
"""
地图数据准备工具：从 PBF 提取指定区域的 OSM XML

用法：
    python prepare_map.py --config ../config.yaml

功能：
    1. 读取配置文件中的 place 或 bbox（若只有 place，自动地理编码获取 bbox）
    2. 使用 osmium 命令行工具从 PBF 提取对应区域的 OSM XML
    3. 输出到 map/ 目录，并在控制台提示如何更新配置

依赖：
    - osmium 命令行工具（非 Python 库）
    - Python: osmnx, pyyaml
"""

import argparse
import yaml
import os
import subprocess
import sys
import osmnx as ox

def load_config(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def ensure_place_bbox(place=None, bbox=None):
    """
    如果提供了 place 而没有 bbox，使用 osmnx 自动地理编码获取 bbox。
    返回 (south, west, north, east)
    """
    if bbox:
        return tuple(bbox)
    if place:
        print(f"地理编码: {place}")
        try:
            gdf = ox.geocode_to_gdf(place)
            minx, miny, maxx, maxy = gdf.total_bounds
            # 确保顺序: south, west, north, east
            south, north = (miny, maxy) if miny <= maxy else (maxy, miny)
            west, east = (minx, maxx) if minx <= maxx else (maxx, minx)
            bbox = (south, west, north, east)
            print(f"  自动获取 bbox: {bbox}")
            return bbox
        except Exception as e:
            print(f"  地理编码失败: {e}")
            raise
    raise ValueError("必须提供 place 或 bbox")

def run_osmium_extract(pbf_path, bbox, output_path):
    """
    调用 osmium extract 命令裁剪 PBF 为 OSM XML。
    bbox: (south, west, north, east)
    """
    if not os.path.exists(pbf_path):
        raise FileNotFoundError(f"PBF 文件不存在: {pbf_path}")
    cmd = [
        "osmium", "extract",
        "-b", f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        pbf_path,
        "-o", output_path
    ]
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"osmium 执行失败: {result.stderr}")
        raise RuntimeError("osmium extract failed")
    print(f"已生成: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="从 PBF 提取 OSM XML 用于离线地图生成")
    parser.add_argument("--config", default="../config.yaml", help="配置文件路径")
    args = parser.parse_args()

    config = load_config(args.config)

    # 确定 PBF 源文件：从 pbf_path 获取（用户把 PBF 放在 map/ 下）
    pbf_path = config.get("pbf_path") or "map/china-latest.osm.pbf"
    # 相对路径处理
    if not os.path.isabs(pbf_path):
        base_dir = os.path.dirname(args.config) if os.path.dirname(args.config) else "."
        pbf_path = os.path.join(base_dir, "..", pbf_path) if "config.yaml" in args.config else os.path.join(base_dir, pbf_path)
        pbf_path = os.path.normpath(pbf_path)

    print(f"使用 PBF 文件: {pbf_path}")
    if not os.path.exists(pbf_path):
        print(f"错误：PBF 文件不存在！请先下载并放置到: {pbf_path}")
        print("下载地址: https://download.geofabrik.de/asia/china.html")
        sys.exit(1)

    # 确定输出 OSM XML 路径
    # 如果 config 有 osm_xml_path，使用它；否则默认为 map/region.osm
    output_rel = config.get("osm_xml_path", "map/hami.osm")
    if not os.path.isabs(output_rel):
        base_dir = os.path.dirname(args.config) if os.path.dirname(args.config) else "."
        output_path = os.path.join(base_dir, "..", output_rel) if "config.yaml" in args.config else os.path.join(base_dir, output_rel)
        output_path = os.path.normpath(output_path)
    else:
        output_path = output_rel

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 已存在？
    if os.path.exists(output_path):
        resp = input(f"文件已存在: {output_path}，是否覆盖？(y/N): ").strip().lower()
        if resp != 'y':
            print("取消操作")
            sys.exit(0)

    # 获取 bbox（优先用 config 里的，否则用 place）
    bbox = config.get("bbox")
    place = config.get("place")
    try:
        bbox_tuple = ensure_place_bbox(place, bbox)
    except Exception as e:
        print(f"无法确定 bbox: {e}")
        sys.exit(1)

    print(f"开始提取区域: bbox={bbox_tuple}")
    print(f"输入 PBF: {pbf_path}")
    print(f"输出 OSM XML: {output_path}")

    # 执行 osmium extract
    try:
        run_osmium_extract(pbf_path, bbox_tuple, output_path)
    except Exception as e:
        print(f"提取失败: {e}")
        sys.exit(1)

    print("\n✅ 提取完成！")
    print("请在 config.yaml 中设置以下内容（如果尚未设置）：")
    print(f"  osm_xml_path: \"{output_rel}\"")
    print(f"  bbox: {list(bbox_tuple)}")
    # 如果 bbox 是从 place 推导的，也提示更新 bbox
    if not config.get("bbox") and place:
        print(f"  # （可选）place 可注释掉")

if __name__ == "__main__":
    main()
