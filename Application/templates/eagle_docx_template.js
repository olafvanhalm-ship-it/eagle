/**
 * Eagle Design System — Word Document Template
 * ==============================================
 * Reusable docx-js template aligned with the Eagle Design System (v1.0).
 * All future Project Eagle documents MUST use this template for visual consistency.
 *
 * Design tokens sourced from: Blueprint/eagle_design_system.md
 *
 * Usage:
 *   const eagle = require('./eagle_docx_template');
 *   const doc = eagle.createDocument({ title, subtitle, version, date, owner, addressees, sections });
 *   eagle.save(doc, 'output.docx');
 *
 * Language: English (per Eagle principle P13)
 */

const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, AlignmentType, LevelFormat,
        HeadingLevel, BorderStyle, WidthType, ShadingType,
        PageNumber, PageBreak, TabStopType, TabStopPosition } = require('docx');
const fs = require('fs');

// ============================================================================
// DESIGN TOKENS (from eagle_design_system.md §2)
// ============================================================================

const TOKENS = {
  // Brand colours (§2.1 — Neutral Scale)
  brand900: "0F172A",   // Primary text, headings
  brand800: "1E293B",   // Sidebar background, strong emphasis
  brand700: "334155",   // Secondary text
  brand600: "475569",   // Tertiary text, placeholders
  brand500: "64748B",   // Disabled text, default borders
  brand100: "F1F5F9",   // Page background, table headers
  brand50:  "F8FAFC",   // Card backgrounds
  white:    "FFFFFF",   // Card surface, inputs

  // Accent colours — Eagle Blue (§2.1)
  accent700: "1D4ED8",  // Primary action buttons, headings
  accent600: "2563EB",  // Hover state
  accent500: "3B82F6",  // Focus rings, selected row
  accent100: "DBEAFE",  // Accent background
  accent50:  "EFF6FF",  // Subtle accent fill

  // Semantic status colours (§2.1 — Maps to Eagle urgency model)
  statusSuccess:  "16A34A",  // PASS, ACCEPTED, GREEN
  statusWarning:  "D97706",  // Warning, AMBER
  statusError:    "DC2626",  // FAIL, RED
  statusCritical: "18181B",  // Overdue, BLACK
  statusInfo:     "2563EB",  // Info notices
  statusNeutral:  "6B7280",  // N/A, pending

  // Status backgrounds (lighter versions for table cells)
  bgSuccess: "DCFCE7",  // Green tint
  bgWarning: "FEF3C7",  // Amber tint
  bgError:   "FEE2E2",  // Red tint
  bgInfo:    "DBEAFE",  // Blue tint
  bgNeutral: "F3F4F6",  // Grey tint

  // Typography (§2.2 — Inter font family; fallback to Calibri for Word)
  fontPrimary: "Calibri",   // Word-safe equivalent of Inter
  fontMono:    "Consolas",  // Word-safe equivalent of JetBrains Mono

  // Font sizes in half-points (§2.2)
  sizeDisplay:  60,  // 30px = 60 half-points — Page titles
  sizeH1:       48,  // 24px — Section headings
  sizeH2:       40,  // 20px — Card/panel titles
  sizeH3:       32,  // 16px — Sub-sections
  sizeBody:     22,  // 11px — Body text (standard Word size, close to 14px screen)
  sizeSmall:    18,  // 9px — Captions, timestamps
  sizeMono:     20,  // 10px — Rule IDs, codes, hashes

  // Spacing in DXA (§2.3 — 4px base, converted: 1px ≈ 15 DXA)
  space2:  120,   // 8px
  space3:  180,   // 12px
  space4:  240,   // 16px
  space6:  360,   // 24px
  space8:  480,   // 32px

  // Borders (§2.4)
  borderColor: "E2E8F0",  // border-default
  borderStrong: "CBD5E1", // border-strong
};

// ============================================================================
// PAGE SETUP — A4 (default for ESMA/EU regulatory documents)
// ============================================================================

const PAGE = {
  width:  11906,  // A4 width in DXA
  height: 16838,  // A4 height in DXA
  margin: 1440,   // 1 inch = 1440 DXA
  get contentWidth() { return this.width - 2 * this.margin; },  // 9026 DXA
};

// ============================================================================
// STYLE DEFINITIONS
// ============================================================================

const STYLES = {
  default: {
    document: {
      run: { font: TOKENS.fontPrimary, size: TOKENS.sizeBody, color: TOKENS.brand900 },
      paragraph: { spacing: { after: 120, line: 276 } },  // 1.15 line spacing
    },
  },
  paragraphStyles: [
    {
      id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: TOKENS.sizeH1, bold: true, font: TOKENS.fontPrimary, color: TOKENS.brand900 },
      paragraph: { spacing: { before: 480, after: 240 }, outlineLevel: 0,
        border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: TOKENS.accent700, space: 8 } } },
    },
    {
      id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: TOKENS.sizeH2, bold: true, font: TOKENS.fontPrimary, color: TOKENS.accent700 },
      paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 1 },
    },
    {
      id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: TOKENS.sizeH3, bold: true, font: TOKENS.fontPrimary, color: TOKENS.brand700 },
      paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 2 },
    },
  ],
};

// ============================================================================
// NUMBERING CONFIGS (bullets and numbered lists)
// ============================================================================

const NUMBERING = {
  config: [
    { reference: "bullets", levels: [{
      level: 0, format: LevelFormat.BULLET, text: "\u2022",
      alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } },
    }]},
    { reference: "numbers", levels: [{
      level: 0, format: LevelFormat.DECIMAL, text: "%1.",
      alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } },
    }]},
    // Use separate references when you need independent numbering sequences
    { reference: "bullets2", levels: [{
      level: 0, format: LevelFormat.BULLET, text: "\u2022",
      alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } },
    }]},
    { reference: "numbers2", levels: [{
      level: 0, format: LevelFormat.DECIMAL, text: "%1.",
      alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } },
    }]},
  ],
};

// ============================================================================
// TABLE HELPERS
// ============================================================================

const defaultBorder = { style: BorderStyle.SINGLE, size: 1, color: TOKENS.borderColor };
const defaultBorders = { top: defaultBorder, bottom: defaultBorder, left: defaultBorder, right: defaultBorder };
const defaultCellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

/**
 * Create a header cell for a table.
 */
function headerCell(text, width) {
  return new TableCell({
    borders: defaultBorders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: TOKENS.brand900, type: ShadingType.CLEAR },
    margins: defaultCellMargins,
    children: [new Paragraph({
      children: [new TextRun({ text, bold: true, color: TOKENS.white, font: TOKENS.fontPrimary, size: TOKENS.sizeBody })],
    })],
  });
}

/**
 * Create a data cell for a table.
 * @param {string} text - Cell content
 * @param {number} width - Column width in DXA
 * @param {object} opts - Optional: { bold, shading, color, mono, align }
 */
function dataCell(text, width, opts = {}) {
  const shading = opts.shading ? { fill: opts.shading, type: ShadingType.CLEAR } : undefined;
  return new TableCell({
    borders: defaultBorders,
    width: { size: width, type: WidthType.DXA },
    shading,
    margins: defaultCellMargins,
    children: [new Paragraph({
      alignment: opts.align,
      children: [new TextRun({
        text,
        bold: opts.bold,
        color: opts.color || TOKENS.brand900,
        font: opts.mono ? TOKENS.fontMono : TOKENS.fontPrimary,
        size: opts.mono ? TOKENS.sizeMono : TOKENS.sizeBody,
      })],
    })],
  });
}

/**
 * Create a status cell with semantic colouring.
 * @param {string} text - Status text (e.g., "PASS", "FAIL", "DONE")
 * @param {number} width - Column width in DXA
 * @param {"success"|"warning"|"error"|"info"|"neutral"} status
 */
function statusCell(text, width, status = "neutral") {
  const colorMap = {
    success: { bg: TOKENS.bgSuccess, fg: TOKENS.statusSuccess },
    warning: { bg: TOKENS.bgWarning, fg: TOKENS.statusWarning },
    error:   { bg: TOKENS.bgError,   fg: TOKENS.statusError },
    info:    { bg: TOKENS.bgInfo,    fg: TOKENS.statusInfo },
    neutral: { bg: TOKENS.bgNeutral, fg: TOKENS.statusNeutral },
  };
  const colors = colorMap[status] || colorMap.neutral;
  return new TableCell({
    borders: defaultBorders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: colors.bg, type: ShadingType.CLEAR },
    margins: defaultCellMargins,
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text, bold: true, color: colors.fg, font: TOKENS.fontPrimary, size: TOKENS.sizeBody })],
    })],
  });
}

// ============================================================================
// PARAGRAPH HELPERS
// ============================================================================

function heading1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
}

function heading2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
}

function heading3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });
}

function para(text, opts = {}) {
  return new Paragraph({
    spacing: opts.spacing,
    alignment: opts.align,
    children: [new TextRun({
      text,
      font: opts.mono ? TOKENS.fontMono : TOKENS.fontPrimary,
      size: opts.size || TOKENS.sizeBody,
      color: opts.color || TOKENS.brand900,
      bold: opts.bold,
      italics: opts.italics,
    })],
  });
}

function emptyPara() {
  return new Paragraph({ children: [] });
}

function bulletItem(text, ref = "bullets") {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    children: [new TextRun({ font: TOKENS.fontPrimary, size: TOKENS.sizeBody, text })],
  });
}

function numberedItem(text, ref = "numbers") {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    children: [new TextRun({ font: TOKENS.fontPrimary, size: TOKENS.sizeBody, text })],
  });
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

// ============================================================================
// DOCUMENT FACTORY
// ============================================================================

/**
 * Create a full Eagle-branded document.
 *
 * @param {object} config
 * @param {string} config.title       - Document title (e.g., "Continuous AIFMD Compliance Assurance")
 * @param {string} config.subtitle    - Optional subtitle
 * @param {string} config.version     - Version string (e.g., "0.3")
 * @param {string} config.date        - Date string (e.g., "1 April 2026")
 * @param {string} config.owner       - Document owner
 * @param {string} config.addressees  - Comma-separated addressees
 * @param {string} config.classification - "Confidential" (default), "Internal", "Public"
 * @param {Array<{version, date, changes}>} config.versionHistory - Version history entries
 * @param {Paragraph[]} config.sections - Array of docx-js Paragraph/Table elements for body content
 * @returns {Document}
 */
function createDocument(config) {
  const {
    title = "Untitled Document",
    subtitle = "",
    version = "0.1",
    date = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }),
    owner = "",
    addressees = "",
    classification = "Confidential",
    versionHistory = [],
    sections = [],
  } = config;

  // Header text for running header
  const headerText = `Project Eagle  |  ${title}  |  v${version}`;

  // Build version history table if provided
  const vhTable = versionHistory.length > 0 ? [
    para("Version History", { bold: true, color: TOKENS.accent700, align: AlignmentType.CENTER }),
    emptyPara(),
    new Table({
      width: { size: 7000, type: WidthType.DXA },
      columnWidths: [1000, 1500, 4500],
      rows: [
        new TableRow({ children: [headerCell("Version", 1000), headerCell("Date", 1500), headerCell("Changes", 4500)] }),
        ...versionHistory.map(vh =>
          new TableRow({ children: [
            dataCell(vh.version, 1000), dataCell(vh.date, 1500), dataCell(vh.changes, 4500),
          ]})
        ),
      ],
    }),
  ] : [];

  return new Document({
    styles: STYLES,
    numbering: NUMBERING,
    sections: [{
      properties: {
        page: {
          size: { width: PAGE.width, height: PAGE.height },
          margin: { top: PAGE.margin, right: PAGE.margin, bottom: PAGE.margin, left: PAGE.margin },
        },
      },
      headers: {
        default: new Header({ children: [
          new Paragraph({
            alignment: AlignmentType.RIGHT,
            border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: TOKENS.accent700, space: 4 } },
            children: [new TextRun({ text: headerText, font: TOKENS.fontPrimary, size: 16, color: TOKENS.brand500 })],
          }),
        ]}),
      },
      footers: {
        default: new Footer({ children: [
          new Paragraph({
            alignment: AlignmentType.CENTER,
            border: { top: { style: BorderStyle.SINGLE, size: 1, color: TOKENS.borderColor, space: 4 } },
            children: [
              new TextRun({ text: `${classification.toUpperCase()}  |  Page `, font: TOKENS.fontPrimary, size: 16, color: TOKENS.brand500 }),
              new TextRun({ children: [PageNumber.CURRENT], font: TOKENS.fontPrimary, size: 16, color: TOKENS.brand500 }),
            ],
          }),
        ]}),
      },
      children: [
        // ── TITLE PAGE ──
        emptyPara(), emptyPara(), emptyPara(), emptyPara(),
        new Paragraph({ alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "PROJECT EAGLE", font: TOKENS.fontPrimary, size: TOKENS.sizeDisplay, bold: true, color: TOKENS.brand900 })] }),
        emptyPara(),
        new Paragraph({ alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "Design Document", font: TOKENS.fontPrimary, size: TOKENS.sizeH2, color: TOKENS.brand600 })] }),
        emptyPara(), emptyPara(),
        new Paragraph({ alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: title, font: TOKENS.fontPrimary, size: TOKENS.sizeH1, bold: true, color: TOKENS.accent700 })] }),
        ...(subtitle ? [
          emptyPara(),
          new Paragraph({ alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: subtitle, font: TOKENS.fontPrimary, size: TOKENS.sizeH2, italics: true, color: TOKENS.brand600 })] }),
        ] : []),
        emptyPara(), emptyPara(), emptyPara(),
        new Paragraph({ alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: `Version ${version}  |  ${date}  |  ${classification}`, font: TOKENS.fontPrimary, size: TOKENS.sizeBody, color: TOKENS.brand500 })] }),
        ...(owner ? [new Paragraph({ alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: `Owner: ${owner}`, font: TOKENS.fontPrimary, size: TOKENS.sizeBody, color: TOKENS.brand500 })] })] : []),
        ...(addressees ? [new Paragraph({ alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: `Addressees: ${addressees}`, font: TOKENS.fontPrimary, size: TOKENS.sizeBody, color: TOKENS.brand500 })] })] : []),
        emptyPara(), emptyPara(),
        ...vhTable,
        pageBreak(),

        // ── BODY SECTIONS ──
        ...sections,
      ],
    }],
  });
}

/**
 * Save document to file.
 */
async function save(doc, outputPath) {
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log(`Eagle document saved: ${outputPath} (${buffer.length} bytes)`);
  return buffer;
}

// ============================================================================
// EXPORTS
// ============================================================================

module.exports = {
  // Design tokens
  TOKENS,
  PAGE,

  // Document factory
  createDocument,
  save,

  // Paragraph helpers
  heading1, heading2, heading3,
  para, emptyPara, bulletItem, numberedItem, pageBreak,

  // Table helpers
  headerCell, dataCell, statusCell,
  defaultBorders, defaultCellMargins,

  // Raw docx-js re-exports for advanced usage
  Table, TableRow, TableCell, Paragraph, TextRun,
  AlignmentType, WidthType, ShadingType, BorderStyle,
};
