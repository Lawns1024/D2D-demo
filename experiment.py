"""
NS-3 Stackelberg D2D Simulation Script (Python Bindings)
请确保运行环境中已编译 NS-3 Python bindings (import ns.core 等)
"""
import ns.core
import ns.network
import ns.internet
import ns.mobility
import ns.wifi
import ns.csma
import ns.applications
import ns.flow_monitor
import math

def calculate_stackelberg_allocation(theta_list, cost_c, max_capacity):
    """阶段一: 数学引擎计算均衡分配带宽 (Mbps)"""
    N = len(theta_list)
    sum_theta = sum(theta_list)
    # 计算最优价格
    p_star = math.sqrt((cost_c * sum_theta) / N)
    
    allocations = []
    for theta in theta_list:
        b_opt = max(0, (theta / p_star) - 1)
        allocations.append(b_opt)
        
    total_b = sum(allocations)
    # 容量约束验证与比例分配
    if total_b > max_capacity:
        allocations = [(b / total_b) * max_capacity for b in allocations]
        
    return allocations, p_star

def run_ns3_simulation():
    # 1. 业务参数初始化
    capacity_mbps = 100.0  # 有线出口总容量 C
    cost_c = 2.0           # 转发损耗 c
    buyers_theta = [25, 35, 45, 15, 50]  # N=5 个买家的偏好
    
    b_allocations, final_price = calculate_stackelberg_allocation(buyers_theta, cost_c, capacity_mbps)
    ns.core.NS_LOG_UNCOND(f"[*] 均衡定价: {final_price:.2f}, 带宽分配结果: {b_allocations}")

    # 2. NS-3 节点与网络拓扑构建
    supplier_node = ns.network.NodeContainer()
    supplier_node.Create(1)
    
    buyer_nodes = ns.network.NodeContainer()
    buyer_nodes.Create(len(buyers_theta))
    
    # 3. 配置带外 D2D 无线信道 (Wi-Fi Ad-hoc 模式模拟 D2D)
    wifi = ns.wifi.WifiHelper()
    wifi.SetStandard(ns.wifi.WIFI_STANDARD_80211n)
    wifiMac = ns.wifi.WifiMacHelper()
    wifiMac.SetType("ns3::AdhocWifiMac") # D2D 去中心化 MAC
    wifiPhy = ns.wifi.YansWifiPhyHelper.Default()
    wifiChannel = ns.wifi.YansWifiChannelHelper.Default()
    wifiPhy.SetChannel(wifiChannel.Create())
    
    # 将无线网卡安装到所有节点
    all_nodes = ns.network.NodeContainer(supplier_node, buyer_nodes)
    devices = wifi.Install(wifiPhy, wifiMac, all_nodes)
    
    # 4. 安装协议栈与 IP 路由
    internet = ns.internet.InternetStackHelper()
    internet.Install(all_nodes)
    ipv4 = ns.internet.Ipv4AddressHelper()
    ipv4.SetBase(ns.network.Ipv4Address("10.1.1.0"), ns.network.Ipv4Mask("255.255.255.0"))
    interfaces = ipv4.Assign(devices)
    
    # 5. 应用层：依据博弈均衡结果设置流量整形
    server_port = 5000
    for i in range(len(buyers_theta)):
        target_rate = f"{b_allocations[i]:.2f}Mbps"
        
        # 接收端配置 (安装在供应者上，代表流量回传/聚合)
        sink = ns.applications.PacketSinkHelper("ns3::UdpSocketFactory", 
                    ns.network.InetSocketAddress(interfaces.GetAddress(0), server_port+i))
        sinkApp = sink.Install(supplier_node.Get(0))
        sinkApp.Start(ns.core.Seconds(1.0))
        sinkApp.Stop(ns.core.Seconds(10.0))
        
        # 发送端配置 (安装在买家上，按照分配的带宽发包)
        onoff = ns.applications.OnOffHelper("ns3::UdpSocketFactory", 
                    ns.network.InetSocketAddress(interfaces.GetAddress(0), server_port+i))
        onoff.SetAttribute("DataRate", ns.network.DataRateValue(ns.network.DataRate(target_rate)))
        onoff.SetAttribute("PacketSize", ns.core.UintegerValue(1024))
        
        clientApp = onoff.Install(buyer_nodes.Get(i))
        clientApp.Start(ns.core.Seconds(2.0))
        clientApp.Stop(ns.core.Seconds(10.0))

    # 6. 运行仿真并开启 FlowMonitor 日志
    flowmon_helper = ns.flow_monitor.FlowMonitorHelper()
    monitor = flowmon_helper.InstallAll()
    
    ns.core.NS_LOG_UNCOND("[*] NS-3 仿真开始启动，正在验证 D2D 链路吞吐量...")
    ns.core.Simulator.Stop(ns.core.Seconds(11.0))
    ns.core.Simulator.Run()
    
    # 导出基于博弈分配的真实数据包流日志
    monitor.SerializeToXmlFile("stackelberg-d2d-results.xml", True, True)
    ns.core.NS_LOG_UNCOND("[*] 仿真结束。结果已导出至 XML 进行延迟/丢包分析。")
    ns.core.Simulator.Destroy()

if __name__ == '__main__':
    run_ns3_simulation()
