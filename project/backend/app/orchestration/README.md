## This folder controls how the agents work together.

A supervisor-based workflow built with LangGraph. The supervisor creates the shared state, delegates work to the agents, collects their results and passes them to the policy engine.

### Files included:
1. **state.py**: The shared state that every agent reads from and writes to.
2. **workflow.py**: Builds the LangGraph graph (nodes, edges, parallel security branch, correction loop).
3. **supervisor.py**: Decides the next step, handles retries and agent failures.
4. **routing.py**: Conditional routing rules used by the graph.

*The **Supervisor** is responsible for connecting the four agents, not duplicating their individual responsibilities.*