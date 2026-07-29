import http from "node:http";
import { captureVisualAudit } from "./capture.mjs";

const port = Number(process.env.HC_VISUAL_AUDIT_PORT || 5015);

function sendJson(response, status, data) {
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  response.end(JSON.stringify(data));
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        reject(new Error("Request body is too large"));
        request.destroy();
      }
    });
    request.on("end", () => {
      if (!body) return resolve({});
      try {
        resolve(JSON.parse(body));
      } catch (err) {
        reject(new Error(`Invalid JSON body: ${err.message}`));
      }
    });
    request.on("error", reject);
  });
}

const server = http.createServer(async (request, response) => {
  if (request.method === "OPTIONS") {
    sendJson(response, 200, { ok: true });
    return;
  }

  if (request.method === "GET" && request.url === "/health") {
    sendJson(response, 200, { ok: true, service: "homecontrol-visual-audit" });
    return;
  }

  if (request.method === "POST" && request.url === "/capture") {
    try {
      const payload = await readBody(request);
      const result = await captureVisualAudit(payload);
      sendJson(response, 200, result);
    } catch (err) {
      sendJson(response, 500, { ok: false, error: err.message });
    }
    return;
  }

  sendJson(response, 404, { ok: false, error: "Not found" });
});

server.listen(port, "0.0.0.0", () => {
  console.log(`HomeControl visual audit server listening on http://0.0.0.0:${port}`);
});
