# Institutional Alpha - Desktop Micro-Widget

This is a C# .NET Micro-Widget designed to run on the desktop and interact with the main Python backend.

## Architecture

- **Framework**: ASP.NET Core MVC / Web API
- **Proxy**: The `SyncController` acts as a proxy, forwarding requests to the Python backend (e.g., `http://localhost:8000/api/valuation`).
- **UI**: Rendered via Razor Views (`Index.cshtml`) with glassmorphic CSS (`wwwroot/css/style.css`).

## Running the Widget

1. Ensure you have the .NET SDK installed.
2. Ensure the Python backend is running locally on port 8000.
3. Navigate to this directory (`src/desktop_widget`).
4. Run the widget:
   ```bash
   dotnet run
   ```
5. The widget will start on a local port (e.g., `http://localhost:5000`).
