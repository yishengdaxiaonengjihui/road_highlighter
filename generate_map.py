#!/usr/bin/env python3
"""
中国国省道路网地图生成器（OSM 在线/PBF 本地）

用法：
    python generate_map.py --config config.yaml

支持两种数据源：
    - 本地 PBF 文件（离线）
    - OSM 在线下载（需要网络）
"""

import argparse
import yaml
import os
import osmnx as ox
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import time

# ================== 配置加载 ==================

def load_config(config_path):
    """加载配置文件，并将路径转换为绝对路径（基于配置文件所在目录）"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    config_dir = os.path.dirname(os.path.abspath(config_path))

    # PBF/XML 路径：相对配置文件的路径
    if config.get('pbf_path'):
        config['pbf_path'] = os.path.normpath(os.path.join(config_dir, config['pbf_path']))
    if config.get('osm_xml_path'):
        config['osm_xml_path'] = os.path.normpath(os.path.join(config_dir, config['osm_xml_path']))

    # 输出路径：固定到 data/outputs 目录
    if config.get('output'):
        output_dir = os.path.join(config_dir, 'data', 'outputs')
        config['output'] = os.path.normpath(os.path.join(output_dir, config['output']))

    return config

# ================== OSM/PBF 数据加载函数 ==================

def load_network_from_pbf_pyrosm(pbf_path, bbox):
    """
    使用 pyrosm 按 bbox 读取 PBF（避免全量加载）。
    bbox: (south, west, north, east) → pyrosm 需要 [min_lon, min_lat, max_lon, max_lat] = [west, south, east, north]
    """
    start = time.time()
    print(f"加载 PBF: {pbf_path}")
    south, west, north, east = bbox
    bbox_pyrosm = [west, south, east, north]  # 列表，非元组
    print(f"  边界框(pyrosm): {bbox_pyrosm}")
    try:
        import pyrosm
    except ImportError:
        raise ImportError("需要 pyrosm，请: pip install pyrosm")
    print("  初始化 OSM 并指定 bbox...")
    osm = pyrosm.OSM(pbf_path, bounding_box=bbox_pyrosm)
    print("  读取驾车路网...")
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    print(f"  提取数据: {len(nodes)} 节点, {len(edges)} 边")
    print("  构建图...")
    G = osm.to_graph(nodes, edges, graph_type="networkx")
    print(f"✅ 完成！耗时: {time.time()-start:.1f}秒")
    return G

def load_network_from_xml(xml_path, bbox=None):
    """OSM XML 加载（保留，备用）"""
    start = time.time()
    print(f"从 XML 加载: {xml_path}")
    G = ox.graph_from_xml(xml_path)
    if bbox:
        G = ox.truncate.truncate_graph_bbox(G, *bbox)
    print(f"  完成: {len(G.nodes())} 节点, {len(G.edges())} 边，耗时: {time.time()-start:.1f}秒")
    return G

def fetch_network_online(place=None, bbox=None):
    """OSM 在线下载（适配 OSMnx v1.0+）"""
    start = time.time()
    G = None
    try:
        if bbox:
            south, west, north, east = bbox
            print(f"在线下载 bbox: S={south}, W={west}, N={north}, E={east}")
            G = ox.graph_from_bbox(bbox=bbox, network_type="drive")
        elif place:
            print(f"在线下载地名: {place}")
            G = ox.graph_from_place(place, network_type="drive")
        else:
            raise ValueError("需要提供 place 或 bbox")
    except Exception as e:
        print(f"❌ 在线下载失败: {str(e)}")
        return None
    if G is not None:
        print(f"✅ 完成: {len(G.nodes())} 节点, {len(G.edges())} 边，耗时: {time.time()-start:.1f}秒")
    return G

# ================== 筛选与绘图 ==================

def filter_roads(G, target_refs):
    edges = ox.graph_to_gdfs(G, nodes=False, fill_edge_geometry=True)
    if "ref" not in edges.columns:
        print("警告：无 'ref' 列，无法筛选目标道路")
        return None
    result = edges[edges["ref"].isin(target_refs)]
    print(f"重点道路: {len(result)} 条边")
    return result

def plot_network(G, target_edges, bg_edges=None, config=None):
    """绘制地图"""
    start = time.time()
    # 配置 matplotlib 中文显示（Windows 系统）
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
    fig, ax = plt.subplots(figsize=(14, 11), dpi=150)
    if bg_edges is not None and len(bg_edges) > 0:
        bg_edges.plot(ax=ax, color=config.get("bg_road_color", "#bdc3c7"),
                      linewidth=config.get("bg_road_width", 1.2),
                      alpha=0.6, zorder=1)
    target_colors = config.get("target_colors", {
        "G575": "#e74c3c", "G331": "#3498db", "G312": "#2ecc71",
        "S656": "#e67e22", "S235": "#9b59b6"
    })
    for ref in config.get("target_roads", []):
        if target_edges is not None and "ref" in target_edges.columns and ref in target_edges["ref"].values:
            sub = target_edges[target_edges["ref"] == ref]
            color = target_colors.get(ref, "#333")
            sub.plot(ax=ax, color=color, linewidth=config.get("target_width", 3.5),
                     alpha=0.9, zorder=2, label=ref)
    ax.set_title(config.get("title", "国省道路网图"), fontsize=18, fontweight='bold')
    ax.axis("off")
    legend_elements = []
    if bg_edges is not None and len(bg_edges) > 0:
        legend_elements.append(Patch(facecolor=config.get("bg_road_color", "#bdc3c7"),
                                   label="其他国省道", alpha=0.6))
    if target_edges is not None and len(target_edges) > 0:
        for ref in config.get("target_roads", []):
            if "ref" in target_edges.columns and ref in target_edges["ref"].values:
                color = target_colors.get(ref, "#333")
                name = config.get("road_names", {}).get(ref, ref)
                legend_elements.append(Patch(facecolor=color, label=f"{ref} ({name})", alpha=0.9))
    ax.legend(handles=legend_elements, loc="upper right", fontsize=10, frameon=True, framealpha=0.9)
    plt.tight_layout()
    output_path = config.get("output", "road_network.svg")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()
    print(f"绘图完成！耗时: {time.time()-start:.1f}秒")
    print(f"地图已保存: {output_path}")

# ================== 主程序 ===================

def main():
    parser = argparse.ArgumentParser(description="中国国省道路网地图生成器（OSM 模式）")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    args = parser.parse_args()
    config = load_config(args.config)
    output_path = config.get("output", "road_network.svg")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bbox = config.get("bbox")
    target_roads = config.get("target_roads", [])
    if not bbox or not target_roads:
        raise ValueError("必须配置 bbox 和 target_roads 参数")
    pbf_path = config.get("pbf_path")
    place = config.get("place")
    target_refs = set(target_roads)
    G = None
    data_source = ""
    # 优先 PBF
    if pbf_path:
        if not os.path.exists(pbf_path):
            print(f"⚠️ PBF 文件不存在: {pbf_path}")
        else:
            print(f"尝试 PBF 加载...")
            try:
                G = load_network_from_pbf_pyrosm(pbf_path, tuple(bbox))
                data_source = "PBF"
            except Exception as e:
                print(f"❌ PBF 加载失败: {e}")
                G = None
    # 备选在线下载
    if G is None:
        print("尝试OSM在线下载...")
        try:
            G = fetch_network_online(place=place, bbox=tuple(bbox))
            data_source = "Online"
        except Exception as e:
            print(f"❌ OSM在线下载失败: {e}")
            raise RuntimeError("无法获取路网数据，请检查配置或网络")
    print(f"✅ 数据源: {data_source}")
    print("筛选道路...")
    all_edges = ox.graph_to_gdfs(G, nodes=False, fill_edge_geometry=True)
    allowed_highways = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified"}
    bg_edges = None
    if "highway" in all_edges.columns:
        if "ref" in all_edges.columns:
            bg_mask = (~all_edges["ref"].isin(target_refs)) & all_edges["highway"].isin(allowed_highways)
            bg_edges = all_edges[bg_mask]
        else:
            bg_mask = all_edges["highway"].isin(allowed_highways)
            bg_edges = all_edges[bg_mask]
            print("警告：数据中无 'ref' 列，背景道路将包含所有等级道路")
    else:
        bg_edges = None
    target_edges = None
    if "ref" in all_edges.columns:
        target_edges = all_edges[all_edges["ref"].isin(target_refs)]
        if len(target_edges) == 0:
            print(f"警告：未找到匹配的重点道路（{target_refs}），请确认这些编号在目标区域存在")
    else:
        print("警告：无 'ref' 字段，无法筛选目标道路")
    print("开始绘图...")
    plot_network(G, target_edges, bg_edges, config)
    print("完成！")

if __name__ == "__main__":
    main()