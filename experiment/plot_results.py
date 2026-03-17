import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import os

def parse_ns3_time(time_str):
    """解析 NS-3 导出的特殊时间格式 (例如: +1000000000.0ns) 并转换为秒"""
    clean_str = time_str.replace('+', '').replace('ns', '')
    return float(clean_str) / 1e9

def analyze_flowmon_xml(file_path):
    if not os.path.exists(file_path):
        print(f"[!] 错误：找不到文件 {file_path}。请确认 NS-3 仿真已成功运行。")
        return None

    tree = ET.parse(file_path)
    root = tree.getroot()
    
    flow_stats = []
    
    print("-" * 50)
    print("NS-3 FlowMonitor 数据解析报告")
    print("-" * 50)
    print(f"{'Flow ID':<10} | {'接收字节 (Bytes)':<18} | {'有效吞吐量 (Mbps)':<15}")
    
    # 遍历 FlowStats 节点
    for flow in root.findall('.//FlowStats/Flow'):
        # 增加安全检查：如果拿不到 flowId，直接跳过该节点
        fid_attr = flow.get('flowId')
        if fid_attr is None:
            continue
            
        flow_id = int(fid_attr)
        rx_bytes = int(flow.get('rxBytes', 0))
        tx_bytes = int(flow.get('txBytes', 0))
        tx_packets = int(flow.get('txPackets', 0))
        rx_packets = int(flow.get('rxPackets', 0))
        lost_packets = int(flow.get('lostPackets', 0))
        
        # 增加时间戳检查
        t_first = flow.get('timeFirstTxPacket')
        t_last = flow.get('timeLastRxPacket')
        
        if t_first and t_last:
            t_start = parse_ns3_time(t_first)
            t_end = parse_ns3_time(t_last)
            duration = t_end - t_start
            
            if duration > 0 and rx_bytes > 0:
                throughput_mbps = (rx_bytes * 8) / duration / 1e6
                derived_loss = max(tx_packets - rx_packets, 0)
                loss_packets = lost_packets if lost_packets > 0 else derived_loss
                loss_rate = (loss_packets / tx_packets) if tx_packets > 0 else 0.0
                flow_stats.append({
                    'id': flow_id,
                    'throughput': throughput_mbps,
                    'goodput': throughput_mbps,
                    'loss_rate': loss_rate
                })
                print(f"Flow {flow_id:<5} | {rx_bytes:<18} | {throughput_mbps:<15.2f}")
            
    return sorted(flow_stats, key=lambda x: x['id'])

def summarize_stats(stats):
    if not stats:
        return {'avg_loss_rate': 0.0, 'avg_goodput': 0.0}
    avg_loss = sum(s['loss_rate'] for s in stats) / len(stats)
    avg_goodput = sum(s['goodput'] for s in stats) / len(stats)
    return {'avg_loss_rate': avg_loss, 'avg_goodput': avg_goodput}

def plot_academic_figure(stats):
    if not stats:
        print("[!] 没有有效的数据流可供绘制。")
        return

    # 在我们的仿真中，5个买家的偏好 Theta 分别是 25, 35, 45, 15, 50
    # 按 Flow ID 顺序映射到 X 轴
    thetas = [25, 35, 45, 15, 50]
    
    # 准备绘图数据
    labels = [f"User {s['id']}\n($\\theta$={thetas[i]})" for i, s in enumerate(stats)]
    throughputs = [s['throughput'] for s in stats]

    # 设置学术绘图风格 (使用全局字体配置)
    plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 12,
        'axes.labelsize': 14,
        'axes.titlesize': 14,
        'xtick.labelsize': 11,
        'ytick.labelsize': 11,
        'legend.fontsize': 11,
        'axes.linewidth': 1.1,
        'xtick.major.width': 1.0,
        'ytick.major.width': 1.0
    })

    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    
    # 绘制柱状图，使用冷色调增强学术感
    bars = ax.bar(labels, throughputs, color='#4C78A8', edgecolor='black', linewidth=0.6, width=0.62)
    
    # 添加数值标签
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, yval + 0.35, f"{yval:.1f}", 
                ha='center', va='bottom', fontsize=10)

    # 标记物理网卡容量瓶颈 (辅助线)
    # 因为总需求超过100Mbps时我们进行了比例分配，所以这里标记100Mbps作为系统硬约束的参考
    ax.axhline(y=100.0, color='#D62728', linestyle='--', linewidth=1.2, label='Physical Capacity Limit $C$')

    # 图表装饰
    ax.set_ylabel('Effective Throughput (Mbps)')
    ax.set_xlabel('Demand Nodes (Followers)')
    ax.set_title('Stackelberg Equilibrium Bandwidth Allocation (NS-3)')
    upper_limit = max(throughputs) * 1.2
    ax.set_ylim(0, max(upper_limit, 105.0)) # 确保容量线可见
    ax.yaxis.grid(True, linestyle='--', alpha=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc='upper right')

    # 紧凑布局并保存为 PNG 图
    plt.tight_layout()
    plt.savefig('d2d_stackelberg_throughput.png', format='png', dpi=600, bbox_inches='tight')
    print("\n[*] 图表渲染完成！已保存为高清图片: d2d_stackelberg_throughput.png")


def _annotate_bars(ax, bars, fmt="{:.1f}", offset=0.3):
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + offset,
            fmt.format(height),
            ha='center',
            va='bottom',
            fontsize=9
        )


def plot_comparison(pricing_stats, greedy_stats):
    if not pricing_stats or not greedy_stats:
        print("[!] 定价或贪婪场景数据缺失，无法绘制对比图。")
        return

    thetas = [25, 35, 45, 15, 50]
    labels = [f"User {s['id']}\n($\\theta$={thetas[i]})" for i, s in enumerate(pricing_stats)]

    pricing_goodput = [s['goodput'] for s in pricing_stats]
    greedy_goodput = [s['goodput'] for s in greedy_stats]
    pricing_loss = [s['loss_rate'] * 1000.0 for s in pricing_stats]
    greedy_loss = [s['loss_rate'] * 100.0 for s in greedy_stats]

    plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 12,
        'axes.labelsize': 13,
        'axes.titlesize': 13,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'legend.fontsize': 11,
        'axes.linewidth': 1.1,
        'xtick.major.width': 1.0,
        'ytick.major.width': 1.0
    })

    x = range(len(labels))
    width = 0.36

    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    pricing_bars = ax.bar([i - width / 2 for i in x], pricing_goodput, width=width, color='#4C78A8',
        edgecolor='black', linewidth=0.6, label='Pricing Goodput')
    greedy_bars = ax.bar([i + width / 2 for i in x], greedy_goodput, width=width, color='#F58518',
        edgecolor='black', linewidth=0.6, label='Greedy Goodput')

    ax.set_ylabel('Goodput (Mbps)')
    ax.set_xlabel('Demand Nodes (Followers)')
    ax.set_title('Pricing vs Greedy: Goodput per User')
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.yaxis.grid(True, linestyle='--', alpha=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc='upper right')

    _annotate_bars(ax, pricing_bars, fmt="{:.2f}", offset=0.25)
    _annotate_bars(ax, greedy_bars, fmt="{:.2f}", offset=0.25)

    plt.tight_layout()
    plt.savefig('d2d_compare_goodput.png', format='png', dpi=600, bbox_inches='tight')
    print("[*] 已保存对比图: d2d_compare_goodput.png")

    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    pricing_loss_bars = ax.bar([i - width / 2 for i in x], pricing_loss, width=width, color='#54A24B',
        edgecolor='black', linewidth=0.6, label='Pricing Loss Rate')
    greedy_loss_bars = ax.bar([i + width / 2 for i in x], greedy_loss, width=width, color='#E45756',
        edgecolor='black', linewidth=0.6, label='Greedy Loss Rate')

    ax.set_ylabel('End-to-End Loss Rate (%)')
    ax.set_xlabel('Demand Nodes (Followers)')
    ax.set_title('Pricing vs Greedy: Loss Rate per User')
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.yaxis.grid(True, linestyle='--', alpha=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc='upper right')

    _annotate_bars(ax, pricing_loss_bars, fmt="{:.2f}", offset=0.3)
    _annotate_bars(ax, greedy_loss_bars, fmt="{:.2f}", offset=0.3)

    plt.tight_layout()
    plt.savefig('d2d_compare_loss.png', format='png', dpi=600, bbox_inches='tight')
    print("[*] 已保存对比图: d2d_compare_loss.png")
    
    # 如果你在图形界面下，可以直接展示
    # plt.show()

if __name__ == "__main__":
    pricing_xml = 'd2d-output-pricing.xml'
    greedy_xml = 'd2d-output-greedy.xml'

    pricing_results = analyze_flowmon_xml(pricing_xml)
    greedy_results = analyze_flowmon_xml(greedy_xml)

    if pricing_results:
        plot_academic_figure(pricing_results)

    if pricing_results and greedy_results:
        plot_comparison(pricing_results, greedy_results)