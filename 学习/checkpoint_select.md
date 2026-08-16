聊天型 Agent：Supervisor Checkpoint。

长时间执行的子工作流（Subgraph）：Supervisor + Agent 双层 Checkpoint。

只有 Agent Checkpoint：除非 Agent 本身就是独立应用，否则很少采用。

短期记忆的作用：1.记得会话上下文内容---不会说明说下面忘记
              2.如果做了短期记忆的存储---下次打开能恢复聊天历史
              3.中断流程后--下次从检查点继续任务

会话列表的文字变化，更新，创建，删除 ---靠pos的表agent_sessions实现
会话上下文=====靠redis实现   