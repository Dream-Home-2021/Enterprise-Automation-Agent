git规则
1.main 永远是可运行 Agent（不允许破坏）
2.每个能力 = 一个 feature/* 分支（tool / memory / graph / rag）
3.LangGraph 按 node 拆分开发（agent / tools / memory / router）
4.Tool Calling 独立封装，不写在 agent core 里
5.所有改动必须可回滚（commit 清晰 + merge 前可运行）