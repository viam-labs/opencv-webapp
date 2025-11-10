import Cookies from "./js-cookie.js";
import * as VIAM from "@viamrobotics/sdk";

let robotClient: VIAM.RobotClient | undefined;
let webappService: VIAM.GenericServiceClient | undefined;

interface FileInfo {
  size: number;
  modified: string;
}

interface PassInfo {
  complete: boolean;
  timestamp: string;
  files: Record<string, FileInfo>;
}

interface PassesData {
  passes: Record<string, PassInfo>;
}

interface MachineSettings {
  host: string;
  serviceName: string;
  apiKeyId: string;
  apiKeySecret: string;
}

interface PortalCookie {
  apiKey: {
    id: string;
    key: string;
  };
  machineId: string;
  hostname: string;
}

async function main() {
  const settings = loadSettingsFromCookie();
  if (!settings) {
    setStatus("Configuration required");
    showError(
      "Missing machine cookie. Please open this app from your viamapplications.com URL after selecting a machine."
    );
    return;
  }

  setStatus("Connecting…");

  try {
    robotClient = await VIAM.createRobotClient({
      host: settings.host,
      credentials: {
        type: "api-key",
        payload: settings.apiKeySecret,
        authEntity: settings.apiKeyId,
      },
      signalingAddress: "https://app.viam.com:443",
    });

    webappService = new VIAM.GenericServiceClient(robotClient, settings.serviceName);
    setStatus(`Connected to ${settings.host}`);

    await refreshPasses();
    wireUi();
  } catch (error) {
    console.error("Connection error:", error);
    setStatus("Connection failed");
    showError(`Failed to connect: ${String(error)}`);
    return;
  }

  window.addEventListener("beforeunload", () => {
    robotClient?.disconnect();
  });
}

async function refreshPasses() {
  if (!webappService) {
    showError("Service is not ready yet.");
    return;
  }

  try {
    const request = VIAM.Struct.fromJson({ command: "list_passes" });
    const raw = (await webappService.doCommand(request)) as unknown;
    if (!isPassesData(raw)) {
      throw new Error("Unexpected response shape from list_passes");
    }
    displayPasses(raw.passes);
  } catch (error) {
    console.error("Error loading passes:", error);
    showError(`Error loading passes: ${String(error)}`);
  }
}

function displayPasses(passes: Record<string, PassInfo>) {
  const container = document.getElementById("passes");
  if (!container) {
    return;
  }

  const sortedPassIds = Object.keys(passes).sort().reverse();

  if (sortedPassIds.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>No calibration passes yet.</p>
      </div>
    `;
    return;
  }

  const html = sortedPassIds
    .map((passId) => {
      const pass = passes[passId];
      const statusClass = pass.complete ? "complete" : "incomplete";
      const statusLabel = pass.complete ? "Complete" : "In Progress";
      const statusBadge = pass.complete ? "status-complete" : "status-incomplete";

      const files = Object.keys(pass.files).filter(
        (filename) => !filename.startsWith(".")
      );
      files.sort();
      const fileItems = files
        .map((filename) => {
          const file = pass.files[filename];
          return `
            <li class="file-item">
              <a href="#" onclick="downloadFile('${passId}', '${filename}'); return false;">${filename}</a>
              <span class="file-meta">
                ${formatBytes(file.size)} | ${file.modified}
              </span>
            </li>
          `;
        })
        .join("");
      const fileCount = files.length;

      return `
        <div class="pass ${statusClass}">
          <div class="pass-header" onclick="togglePass(this)">
            <div class="pass-info">
              <div class="timestamp">🕐 ${pass.timestamp}</div>
              <div class="pass-name-row">
                <span class="pass-name">📁 ${passId}</span>
                <span class="status-badge ${statusBadge}">${statusLabel}</span>
              </div>
            </div>
            <div class="pass-meta">
              <span class="file-count">(${fileCount} files)</span>
              <span class="toggle-icon">▶</span>
            </div>
          </div>
          <div class="pass-content">
            <ul class="file-list">
              ${fileItems}
            </ul>
          </div>
        </div>
      `;
    })
    .join("");

  container.innerHTML = html;

  setTimeout(() => {
    const firstHeader = document.querySelector(".pass-header");
    if (firstHeader) {
      togglePass(firstHeader as HTMLElement);
    }
  }, 100);
}

async function downloadFile(passId: string, filename: string) {
  if (!webappService) {
    alert("Service is not ready yet.");
    return;
  }

  try {
    const request = VIAM.Struct.fromJson({
      command: "get_file",
      pass_id: passId,
      filename,
    });
    const result = (await webappService.doCommand(request)) as unknown;
    const fileResponse = result as {
      filename?: string;
      data?: string;
      size?: number;
    };

    const base64Data = fileResponse.data;
    if (typeof base64Data !== "string") {
      throw new Error("Service response missing file data");
    }

    const blob = base64ToBlob(base64Data);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileResponse?.filename ?? filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Download error:", error);
    alert(`Failed to download file: ${String(error)}`);
  }
}

function base64ToBlob(base64Data: string): Blob {
  const binaryString = atob(base64Data);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i += 1) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return new Blob([bytes]);
}

function togglePass(header: HTMLElement) {
  const content = header.nextElementSibling as HTMLElement | null;
  const icon = header.querySelector(".toggle-icon") as HTMLElement | null;

  if (content && icon) {
    content.classList.toggle("expanded");
    icon.classList.toggle("expanded");
  }
}

function expandAll() {
  document.querySelectorAll<HTMLElement>(".pass-content").forEach((content) => {
    content.classList.add("expanded");
  });
  document.querySelectorAll<HTMLElement>(".toggle-icon").forEach((icon) => {
    icon.classList.add("expanded");
  });
}

function collapseAll() {
  document.querySelectorAll<HTMLElement>(".pass-content").forEach((content) => {
    content.classList.remove("expanded");
  });
  document.querySelectorAll<HTMLElement>(".toggle-icon").forEach((icon) => {
    icon.classList.remove("expanded");
  });
}

function showError(message: string) {
  const container = document.getElementById("passes");
  if (container) {
    container.innerHTML = `
      <div class="empty-state" style="color: red;">
        <p>${message}</p>
      </div>
    `;
  }
}

function setStatus(message: string) {
  const element = document.getElementById("status-text");
  if (element) {
    element.textContent = message;
  }
}

function loadSettingsFromCookie(): MachineSettings | undefined {
  const segments = window.location.pathname.split("/").filter(Boolean);
  if (segments.length < 2) {
    console.warn("Unable to determine machine slug from URL", window.location.pathname);
    return undefined;
  }

  const machineSlug = segments[1];
  const raw = Cookies.get(machineSlug);
  if (!raw) {
    console.warn("Machine cookie not found for slug", machineSlug);
    return undefined;
  }

  try {
    const parsed = JSON.parse(raw) as PortalCookie;
    if (
      !parsed ||
      !parsed.apiKey ||
      typeof parsed.apiKey.id !== "string" ||
      typeof parsed.apiKey.key !== "string" ||
      typeof parsed.hostname !== "string"
    ) {
      throw new Error("Cookie missing required fields");
    }

    const cookieServiceName = Cookies.get(`${machineSlug}-resourcename`);
    const serviceName =
      (cookieServiceName && cookieServiceName.trim()) ||
      (document.querySelector<HTMLMetaElement>('meta[name="viam-service-name"]')?.content?.trim() ?? "");

    if (!serviceName) {
      console.warn(
        "Service name not found in cookies or meta tag; falling back to 'webapp'. " +
          "You can set a meta tag <meta name=\"viam-service-name\" content=\"your-service-name\"> if needed."
      );
    }

    return {
      host: parsed.hostname,
      serviceName: serviceName || "calibration-webapp",
      apiKeyId: parsed.apiKey.id,
      apiKeySecret: parsed.apiKey.key,
    };
  } catch (error) {
    console.error("Failed to parse machine cookie", error);
    return undefined;
  }
}

function formatBytes(size: number | undefined): string {
  if (typeof size !== "number" || !Number.isFinite(size) || size < 0) {
    return "—";
  }
  if (size < 1024) {
    return `${size} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let value = size / 1024;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  const precision = value < 10 ? 1 : 0;
  return `${value.toFixed(precision)} ${units[idx]}`;
}

function isPassInfo(value: unknown): value is PassInfo {
  if (!value || typeof value !== "object") {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.complete === "boolean" &&
    typeof record.timestamp === "string" &&
    typeof record.files === "object" &&
    record.files !== null
  );
}

function isPassesData(value: unknown): value is PassesData {
  if (!value || typeof value !== "object") {
    return false;
  }
  const record = value as Record<string, unknown>;
  if (!record.passes || typeof record.passes !== "object" || record.passes === null) {
    return false;
  }
  const passesRecord = record.passes as Record<string, unknown>;
  return Object.values(passesRecord).every(isPassInfo);
}

function wireUi() {
  const refreshBtn = document.getElementById("refresh-button");
  if (refreshBtn) {
    refreshBtn.onclick = refreshPasses;
  }

  const expandBtn = document.getElementById("expand-all-button");
  if (expandBtn) {
    expandBtn.onclick = expandAll;
  }

  const collapseBtn = document.getElementById("collapse-all-button");
  if (collapseBtn) {
    collapseBtn.onclick = collapseAll;
  }
}

(window as typeof window & { togglePass?: typeof togglePass }).togglePass = togglePass;
(window as typeof window & { downloadFile?: typeof downloadFile }).downloadFile = downloadFile;

document.addEventListener("DOMContentLoaded", () => {
  console.log("Hand-Eye Calibration Viewer initialized.");
  console.log("VIAM SDK loaded:", VIAM);
  console.log("Available VIAM exports:", Object.keys(VIAM));
  console.log("Cookies library loaded:", Cookies);

  const segments = window.location.pathname.split("/").filter(Boolean);
  const machineSlug = segments.length >= 2 ? segments[1] : undefined;
  console.log("Resolved machine slug:", machineSlug ?? "(none)");

  if (machineSlug) {
    const cookieData = Cookies.get(machineSlug);
    if (cookieData) {
      console.log("Machine cookie found.");
    } else {
      console.warn("No machine cookie found for slug:", machineSlug);
    }
  } else {
    console.warn("Unable to determine machine slug from URL:", window.location.pathname);
  }

  main().catch((error: unknown) => {
    console.error("Encountered an unexpected error:", error);
    showError(`Unexpected error: ${String(error)}`);
    setStatus("Error");
  });
});
