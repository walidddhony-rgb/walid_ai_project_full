Walid AI
Walid AI is a local desktop AI assistant focused on Arabic-first interaction, code-aware workspace assistance, file indexing, and extensible offline-friendly tooling.

Current scope
The project currently combines a Qt desktop UI, a local persistence layer, file tools, a learning/memory layer, and optional voice features. The goal is to provide a private desktop assistant that can work on local files and project folders without requiring a cloud-first architecture.

Architecture
text
app.py
  -> walid_ai.ui.main_window.MainWindow
      -> walid_ai.agent.controller.AgentController
          -> walid_ai.services.app_services.AppServices
              -> DatabaseManager
              -> PermissionManager
              -> LearningManager
              -> ChatService
Layers
ui/: Qt widgets and presentation only.

agent/: thin coordination layer between UI and services.

services/: business logic and orchestration, isolated from GUI widgets.

memory/: SQLite persistence for history, indexed files, operations, and learned memory.

security/: workspace-safe permission checks.

tools/: reusable filesystem, indexing, and code analysis helpers.

voice/: speech-to-text and text-to-speech adapters.

learning/: high-level memory and preference storage behavior.

Why this refactor
The previous shape had several maturity blockers:

broken contracts between main_window.py, database.py, and learning_manager.py

duplicated permission logic in controller.py and security/permissions.py

UI code carrying business logic directly

incomplete package initialization files

minimal project documentation for contributors

This patch resolves those issues by making the GUI thinner, consolidating permissions into one source, and introducing a service layer.

Run
bash
pip install -r requirements.txt
python app.py
Next milestones
Replace the stub model callback with a real Ollama chat service.

Move voice operations to background workers integrated with Qt signals.

Add unit tests for DatabaseManager, PermissionManager, and ChatService.

Introduce structured logging across all modules.

Add settings management for model, language, and workspace preferences.

Limits
This repository is still a work in progress. The desktop shell exists, but production maturity still requires stronger tests, logging, error reporting, and a fully integrated model service.
