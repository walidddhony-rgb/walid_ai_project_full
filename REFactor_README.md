# Refactored agent files

This package converts the previously monolithic `AgentController` logic into the current repository architecture:

- `walid_ai/agent/controller.py`: thin coordination layer
- `walid_ai/services/agent_workflow_service.py`: planning, permissions, local analysis, validation
- `walid_ai/services/research_service.py`: academic/web research logic
- `walid_ai/services/patch_service.py`: safe patch writing with backups

The split matches the repository README architecture, where `agent/` is a light orchestration layer and `services/` contains business logic.
