# Campus D2D Stackelberg Demo

这是一个从论文策略落地的可视化系统 demo，包含：

- 学生视角：查看各学生在 Stackelberg 与 Greedy 下可获得带宽
- 管理员视角：查看系统 Goodput、丢包率、供应者效用、均衡价格
- 后端 API：`FastAPI` 提供仿真接口

## 目录

- `backend/app/main.py`：后端与核心策略逻辑
- `frontend/index.html`：前端可视化页面（双视角）
- `experiment.py`：NS-3 Python bindings 仿真脚本（论文补充）
- `run_demo.py`：本地启动入口

## 快速运行（Windows PowerShell）

```powershell
cd e:\llxpaper\project1\demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_demo.py
```

启动后访问：

- `http://127.0.0.1:8000`
- 健康检查：`http://127.0.0.1:8000/api/health`

## 接口

- `POST /api/simulate`

请求示例：

```json
{
  "buyers_theta": [25, 35, 45, 15, 50],
  "cost_c": 2.0,
  "capacity_mbps": 100.0
}
```

## 说明

当前后端默认使用论文公式与容量约束做快速计算对比，便于课堂演示与答辩展示。
你可以后续在 `backend/app/main.py` 中扩展 NS-3 结果解析（如读取 FlowMonitor XML）来替换近似指标。 
