from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Dict
import math
from pathlib import Path


class SimulationRequest(BaseModel):
    buyers_theta: List[float] = Field(default=[25, 35, 45, 15, 50])
    cost_c: float = Field(default=2.0, gt=0)
    capacity_mbps: float = Field(default=100.0, gt=0)


class BuyerResult(BaseModel):
    buyer_id: int
    theta: float
    allocation_stackelberg: float
    allocation_greedy: float


class SimulationResponse(BaseModel):
    p_star: float
    total_demand_raw: float
    total_allocation_stackelberg: float
    total_allocation_greedy: float
    loss_rate_stackelberg: float
    loss_rate_greedy: float
    goodput_stackelberg: float
    goodput_greedy: float
    supplier_utility: float
    buyers: List[BuyerResult]


def stackelberg_allocation(theta_list: List[float], cost_c: float, capacity: float):
    n = len(theta_list)
    theta_sum = sum(theta_list)
    p_star = math.sqrt((cost_c * theta_sum) / n)

    raw = [max(0.0, theta / p_star - 1.0) for theta in theta_list]
    raw_sum = sum(raw)
    if raw_sum > capacity and raw_sum > 0:
        alloc = [x / raw_sum * capacity for x in raw]
    else:
        alloc = raw

    return p_star, raw, alloc


def greedy_allocation(theta_list: List[float], capacity: float):
    # 无定价约束：按 theta 比例申请，放大系数模拟贪婪
    raw = [max(0.0, t * 0.8) for t in theta_list]
    raw_sum = sum(raw)
    if raw_sum <= capacity:
        return raw, raw
    # 链路过载：实际只能通过容量，按请求比例压缩
    served = [x / raw_sum * capacity for x in raw]
    return raw, served


def estimate_metrics(total_requested: float, total_served: float):
    if total_requested <= 0:
        return 0.0, 0.0
    loss_rate = max(0.0, (total_requested - total_served) / total_requested)
    return loss_rate, total_served


app = FastAPI(title="Campus D2D Stackelberg Demo", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/simulate", response_model=SimulationResponse)
def simulate(req: SimulationRequest):
    p_star, stack_raw, stack_alloc = stackelberg_allocation(req.buyers_theta, req.cost_c, req.capacity_mbps)
    greedy_raw, greedy_served = greedy_allocation(req.buyers_theta, req.capacity_mbps)

    stack_total_raw = sum(stack_raw)
    stack_total_alloc = sum(stack_alloc)
    greedy_total_raw = sum(greedy_raw)
    greedy_total_served = sum(greedy_served)

    loss_stack, goodput_stack = estimate_metrics(stack_total_raw, stack_total_alloc)
    loss_greedy, goodput_greedy = estimate_metrics(greedy_total_raw, greedy_total_served)

    supplier_utility = sum((p_star - req.cost_c) * b for b in stack_alloc)

    buyers = [
        BuyerResult(
            buyer_id=i + 1,
            theta=req.buyers_theta[i],
            allocation_stackelberg=round(stack_alloc[i], 3),
            allocation_greedy=round(greedy_served[i], 3),
        )
        for i in range(len(req.buyers_theta))
    ]

    return SimulationResponse(
        p_star=round(p_star, 4),
        total_demand_raw=round(stack_total_raw, 3),
        total_allocation_stackelberg=round(stack_total_alloc, 3),
        total_allocation_greedy=round(greedy_total_served, 3),
        loss_rate_stackelberg=round(loss_stack, 4),
        loss_rate_greedy=round(loss_greedy, 4),
        goodput_stackelberg=round(goodput_stack, 3),
        goodput_greedy=round(goodput_greedy, 3),
        supplier_utility=round(supplier_utility, 3),
        buyers=buyers,
    )


frontend_dist = Path(__file__).resolve().parents[2] / "frontend"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
