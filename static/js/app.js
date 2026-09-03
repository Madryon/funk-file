const actions = {
  merge: ["Merge PDF","Select two or more PDFs/images to combine."],
  split: ["Split PDF","Split by page ranges or fixed page chunks."],
  compress: ["Compress PDF","Reduce PDF size while keeping it usable."],
  "pdf-to-word": ["PDF → Word","Convert a PDF into an editable DOCX."],
  "word-to-pdf": ["Word → PDF","Convert a Word/Office document into PDF."],
  "pdf-to-jpg": ["PDF → JPG","Render each PDF page as a JPG."],
  "pdf-to-png": ["PDF → PNG","Render each PDF page as a PNG."],
  "jpg-to-pdf": ["JPG → PDF","Turn one or more JPG images into a PDF."],
  "png-to-pdf": ["PNG → PDF","Turn one or more PNG images into a PDF."],
  rotate: ["Rotate PDF","Rotate all pages or selected pages."],
  "delete-pages": ["Delete Pages","Remove selected pages from the PDF."],
  "extract-pages": ["Extract Pages","Keep only the selected pages."],
  watermark: ["Watermark","Add a text watermark to every page."],
  protect: ["Protect PDF","Add a password to the PDF."],
  unlock: ["Unlock PDF","Remove a password you already know."]
};

const toolButtons = document.querySelectorAll(".tool");
const form = document.getElementById("toolForm");
const fileInput = document.getElementById("files");
const dropzone = document.getElementById("dropzone");
const choose = document.getElementById("choose");
const fileList = document.getElementById("fileList");
const options = document.getElementById("options");
const actionInput = document.getElementById("action");
const title = document.getElementById("toolTitle");
const hint = document.getElementById("toolHint");
const status = document.getElementById("status");
const submit = document.getElementById("submit");

let selectedAction = "merge";
let files = [];

function renderOptions() {
  const common = {
    split: `<label class="option">Split mode<select name="split_mode" id="splitMode"><option value="ranges">Page ranges</option><option value="fixed">Fixed chunks</option></select></label><label class="option" id="pagesOpt">Pages / ranges<input name="pages" placeholder="1-3,5-7"></label><label class="option" id="chunkOpt" hidden>Pages per file<input name="chunk_size" type="number" min="1" value="2"></label>`,
    compress: `<label class="option">Compression<select name="level"><option value="recommended">Recommended</option><option value="extreme">Extreme</option><option value="low">Low</option></select></label>`,
    rotate: `<label class="option">Rotation<select name="degrees"><option>90</option><option>180</option><option>270</option></select></label><label class="option">Pages (optional)<input name="pages" placeholder="all or 1,3-5"></label>`,
    "delete-pages": `<label class="option">Pages to delete<input name="pages" placeholder="2,4-6" required></label>`,
    "extract-pages": `<label class="option">Pages to keep<input name="pages" placeholder="1-3,7" required></label>`,
    watermark: `<label class="option">Watermark text<input name="text" value="CONFIDENTIAL" required></label><label class="option">Opacity<input name="opacity" type="number" min=".05" max="1" step=".05" value=".25"></label><label class="option">Rotation<input name="rotation" type="number" value="45"></label>`,
    protect: `<label class="option">Password<input name="password" type="password" minlength="1" required></label>`,
    unlock: `<label class="option">Current password<input name="password" type="password" required></label>`
  };
  options.innerHTML = common[selectedAction] || "";
  const splitMode = document.getElementById("splitMode");
  if (splitMode) splitMode.addEventListener("change", () => {
    const fixed = splitMode.value === "fixed";
    document.getElementById("pagesOpt").hidden = fixed;
    document.getElementById("chunkOpt").hidden = !fixed;
  });
}

function setAction(action) {
  selectedAction = action;
  actionInput.value = action;
  title.textContent = actions[action][0];
  hint.textContent = actions[action][1];
  toolButtons.forEach(b => b.classList.toggle("active", b.dataset.action === action));
  renderOptions();
  files = [];
  fileInput.value = "";
  renderFiles();
  status.textContent = "";
  status.className = "status";
}

function renderFiles() {
  fileList.innerHTML = files.map((f,i) =>
    `<div class="file-row"><span>${i+1}. ${escapeHtml(f.name)}</span><span>${formatBytes(f.size)}</span></div>`
  ).join("");
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function formatBytes(n) {
  if (n < 1024*1024) return `${Math.round(n/1024)} KB`;
  return `${(n/1024/1024).toFixed(1)} MB`;
}
function addFiles(list) {
  const incoming = [...list];
  if (selectedAction !== "merge" && selectedAction !== "jpg-to-pdf" && selectedAction !== "png-to-pdf") {
    files = incoming.slice(0,1);
  } else {
    files = [...files, ...incoming];
  }
  renderFiles();
}

toolButtons.forEach(b => b.addEventListener("click", () => setAction(b.dataset.action)));
choose.addEventListener("click", e => { e.stopPropagation(); fileInput.click(); });
dropzone.addEventListener("click", e => {
  if (!e.target.closest("button")) fileInput.click();
});
fileInput.addEventListener("change", () => addFiles(fileInput.files));
dropzone.addEventListener("dragover", e => { e.preventDefault(); dropzone.style.borderColor = "#111"; });
dropzone.addEventListener("dragleave", () => dropzone.style.borderColor = "");
dropzone.addEventListener("drop", e => {
  e.preventDefault(); dropzone.style.borderColor = ""; addFiles(e.dataTransfer.files);
});

form.addEventListener("submit", async e => {
  e.preventDefault();
  status.className = "status";
  if (!files.length) {
    status.textContent = "Please select a file.";
    status.classList.add("error");
    return;
  }
  const data = new FormData(form);
  data.delete("files");
  files.forEach(f => data.append("files", f));
  submit.disabled = true;
  status.textContent = "Processing…";

  try {
    const res = await fetch("/api/process", { method: "POST", body: data });
    if (!res.ok) {
      let msg = "Processing failed.";
      try { msg = (await res.json()).error || msg; } catch {}
      throw new Error(msg);
    }
    const data = await response.json();

if (data.success) {
    addDownloadItem(data.filename, data.download_url);
}
    function addDownloadItem(filename, downloadUrl) {
    const downloadList = document.getElementById("downloadList");

    const item = document.createElement("div");
    item.className = "download-item";

    item.innerHTML = `
        <div class="download-info">
            <span class="download-filename">${filename}</span>
            <span class="download-status">Ready</span>
        </div>

        <a
            class="download-button"
            href="${downloadUrl}"
            download
        >
            Download
        </a>
    `;

    downloadList.prepend(item);
}
    URL.revokeObjectURL(url);
    status.textContent = "Done — your file is ready.";
    status.classList.add("ok");
  } catch (err) {
    status.textContent = err.message || "Something went wrong.";
    status.classList.add("error");
  } finally {
    submit.disabled = false;
  }
});

setAction("merge");
