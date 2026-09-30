/* =========================
   YOU LOVE PDF
   COMMON WEBSITE JAVASCRIPT
========================= */


/* =========================
   OPEN TOOL
========================= */

function openTool(tool) {

    const toolPages = {

        "compress": "tools/compress.html",

        "merge": "tools/merge.html",

        "split": "tools/split.html",

        "jpg-to-pdf": "tools/jpg-to-pdf.html",

        "pdf-to-jpg": "tools/pdf-to-jpg.html"

    };


    if (toolPages[tool]) {

        window.location.href = toolPages[tool];

    } else {

        console.error(
            "Tool page not found:",
            tool
        );

    }

}
