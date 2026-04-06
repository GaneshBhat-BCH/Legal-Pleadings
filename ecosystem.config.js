module.exports = {
    apps: [{
        name: "legal-pleadings-api",
        script: "backend/venv/Scripts/uvicorn.exe",
        args: "app.main:app --host 0.0.0.0 --port 8000",
        cwd: "./backend",
        instances: 1,
        autorestart: true,
        watch: false,
        max_memory_restart: "1G",
        env: {
            NODE_ENV: "production",
        }
    }]
};
