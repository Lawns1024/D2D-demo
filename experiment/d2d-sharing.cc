#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/wifi-module.h"
#include "ns3/mobility-module.h"
#include "ns3/applications-module.h"
#include "ns3/flow-monitor-module.h"
#include <cmath>
#include <vector>
#include <algorithm>
#include <sstream>
#include <iomanip>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE ("D2DStackelbergSharing");

struct ScenarioSummary
{
    double avg_loss_rate = 0.0;
    double avg_goodput_mbps = 0.0;
    uint32_t flow_count = 0;
};

static ScenarioSummary RunScenario(const std::string &label,
                                                                     const std::vector<double> &allocations,
                                                                     uint32_t nBuyers,
                                                                     const std::vector<double> &thetas,
                                                                     const std::string &outputXml)
{
    NS_LOG_UNCOND ("\n[***] 运行场景: " << label);

    // --- 1. NS-3 物理网络构建 ---
    NodeContainer allNodes;
    allNodes.Create (nBuyers + 1);

    Ptr<Node> supplier = allNodes.Get (0); // 节点 0 为供应者
    NodeContainer buyers;
    for (uint32_t i = 1; i <= nBuyers; ++i) {
        buyers.Add (allNodes.Get (i));     // 节点 1~N 为需求者
    }

    WifiHelper wifi;
    wifi.SetStandard (WIFI_STANDARD_80211n);
    YansWifiPhyHelper wifiPhy;
    YansWifiChannelHelper wifiChannel = YansWifiChannelHelper::Default ();
    wifiPhy.SetChannel (wifiChannel.Create ());

    WifiMacHelper wifiMac;
    wifiMac.SetType ("ns3::AdhocWifiMac");
    NetDeviceContainer allDevices = wifi.Install (wifiPhy, wifiMac, allNodes);

    MobilityHelper mobility;
    mobility.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
    mobility.Install (allNodes);

    InternetStackHelper stack;
    stack.Install (allNodes);
    Ipv4AddressHelper address;
    address.SetBase ("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign (allDevices);

    // --- 2. 流量应用 ---
    uint16_t port = 9;
    for (uint32_t i = 0; i < nBuyers; ++i) {
        Address sinkAddress (InetSocketAddress (interfaces.GetAddress (i + 1), port));
    PacketSinkHelper packetSinkHelper ("ns3::UdpSocketFactory", sinkAddress);
        ApplicationContainer sinkApp = packetSinkHelper.Install (buyers.Get (i));
        sinkApp.Start (Seconds (1.0));
        sinkApp.Stop (Seconds (10.0));

    OnOffHelper onoff ("ns3::UdpSocketFactory", sinkAddress);
        onoff.SetAttribute ("OnTime", StringValue ("ns3::ConstantRandomVariable[Constant=1]"));
        onoff.SetAttribute ("OffTime", StringValue ("ns3::ConstantRandomVariable[Constant=0]"));

        double rate_mbps = std::max(allocations[i], 0.01);
        std::ostringstream rateString;
        rateString << std::fixed << std::setprecision(2) << rate_mbps << "Mbps";
        onoff.SetAttribute ("DataRate", DataRateValue (DataRate (rateString.str())));
        onoff.SetAttribute ("PacketSize", UintegerValue (1024));

        ApplicationContainer clientApp = onoff.Install (supplier);
        clientApp.Start (Seconds (1.1));
        clientApp.Stop (Seconds (10.0));

        NS_LOG_UNCOND ("    -> User " << i + 1 << " (Theta=" << thetas[i]
                                                                    << ") 发送速率: " << rate_mbps << " Mbps");
    }

    // --- 3. 性能监控 ---
    FlowMonitorHelper flowmon;
    Ptr<FlowMonitor> monitor = flowmon.InstallAll ();

    NS_LOG_UNCOND ("[*] NS-3 物理层仿真开始运行 (耗时 10 秒)...");
    Simulator::Stop (Seconds (11.0));
    Simulator::Run ();

    monitor->CheckForLostPackets ();
    monitor->SerializeToXmlFile (outputXml, true, true);

    ScenarioSummary summary;
    auto stats = monitor->GetFlowStats ();
    for (const auto &entry : stats) {
        const auto &flow = entry.second;
        if (flow.txPackets == 0) {
            continue;
        }
        double duration = (flow.timeLastRxPacket - flow.timeFirstTxPacket).GetSeconds ();
        if (duration <= 0) {
            duration = (flow.timeLastTxPacket - flow.timeFirstTxPacket).GetSeconds ();
        }
        if (duration <= 0) {
            continue;
        }

        uint64_t derived_loss = 0;
        if (flow.txPackets > flow.rxPackets) {
            derived_loss = flow.txPackets - flow.rxPackets;
        }
        uint64_t loss_packets = (flow.lostPackets > 0) ? flow.lostPackets : derived_loss;
        double loss_rate = static_cast<double>(loss_packets) / flow.txPackets;
        double goodput_mbps = (flow.rxBytes * 8.0) / duration / 1e6;

        summary.avg_loss_rate += loss_rate;
        summary.avg_goodput_mbps += goodput_mbps;
        summary.flow_count++;
    }

    if (summary.flow_count > 0) {
        summary.avg_loss_rate /= summary.flow_count;
        summary.avg_goodput_mbps /= summary.flow_count;
    }

    Simulator::Destroy ();

    NS_LOG_UNCOND ("[*] 场景 " << label << " 平均丢包率: "
                                                         << summary.avg_loss_rate * 100.0 << "%");
    NS_LOG_UNCOND ("[*] 场景 " << label << " 平均 Goodput: "
                                                         << summary.avg_goodput_mbps << " Mbps");
    NS_LOG_UNCOND ("[*] 探针数据已写入: " << outputXml);
    return summary;
}

int main (int argc, char *argv[])
{
    // --- 1. 参数设置与命令行解析 ---
    uint32_t nBuyers = 5;
    double capacity = 100.0; // 物理网卡瓶颈 (Mbps)
    double costC = 0.8;     // 转发损耗

    CommandLine cmd (__FILE__);
    cmd.AddValue ("nBuyers", "Number of buyer nodes", nBuyers);
    cmd.AddValue ("capacity", "Supplier bottleneck capacity (Mbps)", capacity);
    cmd.AddValue ("cost", "Marginal cost c", costC);
    cmd.Parse (argc, argv);

    // 定义5个终端用户的偏好值 Theta
    std::vector<double> thetas = {25, 35, 45, 15, 50};
    if (nBuyers > thetas.size()) nBuyers = thetas.size(); // 防止越界

    // --- 2. 斯塔克尔伯格博弈逻辑计算 ---
    NS_LOG_UNCOND ("\n[*] 启动 Stackelberg 博弈逻辑结算...");
    
    double sumTheta = 0;
    for (uint32_t i = 0; i < nBuyers; ++i) sumTheta += thetas[i];

    // 计算最优定价 p* = sqrt(c * Theta / N)
    double pStar = std::sqrt((costC * sumTheta) / nBuyers);
    NS_LOG_UNCOND ("[*] 经博弈计算，系统最优定价 p* = " << pStar);
    
    std::vector<double> rawDemands;
    double totalDemand = 0;
    for (uint32_t i = 0; i < nBuyers; ++i) {
        double b = std::max(0.0, (thetas[i] / pStar) - 1.0);
        rawDemands.push_back(b);
        totalDemand += b;
    }

    // 容量约束处理 (若总需求 > C，执行比例公平降级)
    std::vector<double> finalAllocations;
    if (totalDemand > capacity) {
        NS_LOG_UNCOND ("(!) 警告：总需求 (" << totalDemand << " Mbps) 突破网卡极限！触发比例公平分配策略...");
        for (double b : rawDemands) {
            finalAllocations.push_back((b / totalDemand) * capacity);
        }
    } else {
        NS_LOG_UNCOND ("[*] 网络容量充足，完全满足所有用户需求。");
        finalAllocations = rawDemands;
    }

    for (uint32_t i = 0; i < nBuyers; ++i) {
        NS_LOG_UNCOND ("    -> User " << i+1 << " (Theta=" << thetas[i] << ") 分配带宽: " << finalAllocations[i] << " Mbps");
    }
    NS_LOG_UNCOND ("--------------------------------------------------");

    double greedyPrice = 0.6; // 近似“无定价约束”时的极低价格
    std::vector<double> greedyAllocations;
    double greedyTotal = 0.0;
    for (uint32_t i = 0; i < nBuyers; ++i) {
        double greedyDemand = std::max(0.0, (thetas[i] / greedyPrice) - 1.0);
        greedyAllocations.push_back(greedyDemand);
        greedyTotal += greedyDemand;
    }
    NS_LOG_UNCOND ("[Greedy] 无定价约束总需求 = " << greedyTotal
                                            << " Mbps (C=" << capacity << ")");

    ScenarioSummary pricingSummary = RunScenario(
        "Stackelberg 定价+容量约束",
        finalAllocations,
        nBuyers,
        thetas,
        "d2d-output-pricing.xml");

    ScenarioSummary greedySummary = RunScenario(
        "无定价约束的贪婪请求",
        greedyAllocations,
        nBuyers,
        thetas,
        "d2d-output-greedy.xml");

    NS_LOG_UNCOND ("\n================= 对比汇总 =================");
    NS_LOG_UNCOND ("Pricing  平均丢包率: " << pricingSummary.avg_loss_rate * 100.0
                                           << "% | 平均 Goodput: "
                                           << pricingSummary.avg_goodput_mbps << " Mbps");
    NS_LOG_UNCOND ("Greedy   平均丢包率: " << greedySummary.avg_loss_rate * 100.0
                                           << "% | 平均 Goodput: "
                                           << greedySummary.avg_goodput_mbps << " Mbps");
    NS_LOG_UNCOND ("============================================\n");

    NS_LOG_UNCOND ("[*] 仿真结束！对比数据已写入 XML。\n");
    return 0;
}