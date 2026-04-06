# PM2 Deployment Guide (Windows)

Because Docker is incompatible with your system, you have chosen to use `PM2`, the industry-standard node process manager, to keep your FastAPI server alive. PM2 will run your Python project safely in the background, automatically restarting it if it crashes.

---

## 1. Prerequisites (Install Node.js)
Because PM2 is a Node.js tool, you must install Node onto this VM.
1. Open PowerShell and run:
   ```powershell
   winget install OpenJS.NodeJS
   ```
2. Close PowerShell, then open a **new** PowerShell window so it recognizes the `node` and `npm` commands.

## 2. Install PM2
In your new PowerShell terminal, install PM2 globally:
```powershell
npm install -g pm2
```

---

## 3. Start the API Service
I have placed an `ecosystem.config.js` file in your project folder which contains the exact startup logic for the FastAPI app. Start the service by running:

```powershell
cd "C:\Users\srvidhCH273818\Documents\Legal Pleadings"
pm2 start ecosystem.config.js
```
*Your server is now instantly running in the background on port 8000!*

---

## 4. Make It Survive Reboots
To ensure PM2 automatically starts up when the Windows Server boots up natively:
1. First, install the Windows PM2 startup module:
   ```powershell
   npm install -g pm2-windows-startup
   ```
2. Initialize and lock the startup config:
   ```powershell
   pm2-startup install
   pm2 save
   ```

---

## Useful PM2 Commands for the Future:
* **Monitor Live Traffic / Printing:** `pm2 logs`
* **Restart the code (after Git Pulls):** `pm2 restart legal-pleadings-api`
* **Stop the Server:** `pm2 stop legal-pleadings-api`
* **View running processes:** `pm2 list`
