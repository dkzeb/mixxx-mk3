# Settings Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder settings panel with a tabbed settings system (General/Library/Network) navigable via D buttons and 4D nav encoder, with a command executor daemon for system actions.

**Architecture:** The settings panel is implemented across three layers: (1) Skin XML defines the static layout — tab bar, item rows per tab, cursor highlight via CO visibility bindings. (2) JS mapping manages all state (active tab, cursor position, confirm mode) and sets skin COs to drive the display. (3) A Python command executor daemon watches `/tmp/mk3-settings-cmd` for system commands (reboot, shutdown, mount, tailscale, etc.) that JS cannot execute directly. The Mixxx skin system cannot display dynamic text from JS, so info items (IP, version) show static labels only — dynamic values are deferred to QML rendering.

**Tech Stack:** Mixxx skin XML, Mixxx JS controller API, Python 3 (daemon), Tailscale, qrencode

**Spec:** `docs/superpowers/specs/2026-03-31-settings-panel-design.md`

---

### Task 1: JS Settings Data Model and Tab Definitions

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js:300-306` (state variables)

This task adds the settings state variables and tab content definitions. Each tab is an array of item objects describing type, label, and action key. The cursor skips `"info"` type items.

- [ ] **Step 1: Replace existing settings state with full data model**

In `mapping/Native-Instruments-Maschine-MK3.js`, replace the single `settingsVisible` line (line 305) and add after line 306 (`padMode`):

```javascript
MaschineMK3.settingsVisible = false;    // whether the settings panel is shown
MaschineMK3.settingsTab     = 0;        // 0=General, 1=Library, 2=Network
MaschineMK3.settingsCursor  = 0;        // index into current tab's selectable items
MaschineMK3.settingsConfirm = false;    // true when awaiting destructive confirmation
MaschineMK3.settingsConfirmTimer = 0;   // timer ID for auto-cancel

// Settings tab definitions: each item has type, label, and action key.
// type: "action" (chevron, NavPush executes), "toggle" (switch), "info" (read-only, cursor skips)
// confirm: true for destructive actions requiring two-step confirmation
MaschineMK3.settingsTabs = [
    { name: "GENERAL", items: [
        { type: "action",  label: "Reboot",              action: "reboot",    confirm: true },
        { type: "action",  label: "Shutdown",            action: "shutdown",  confirm: true },
        { type: "action",  label: "Check for Updates",   action: "update" },
        { type: "toggle",  label: "Auto-update on boot", action: "autoupdate", stateKey: "settingsAutoUpdate" },
        { type: "info",    label: "Version" },
    ]},
    { name: "LIBRARY", items: [
        { type: "action",  label: "Rescan Library",      action: "rescan" },
        { type: "action",  label: "Mount USB Drive",     action: "mount-usb" },
        { type: "action",  label: "Unmount USB Drive",   action: "unmount-usb" },
        { type: "info",    label: "Library Location" },
    ]},
    { name: "NETWORK", items: [
        { type: "info",    label: "IP Address" },
        { type: "info",    label: "Hostname" },
        { type: "info",    label: "WiFi Network" },
        { type: "action",  label: "WiFi Select",         action: "wifi-select" },
        { type: "toggle",  label: "Tailscale",           action: "tailscale", stateKey: "settingsTailscale" },
        { type: "toggle",  label: "Hotspot",             action: "hotspot",   stateKey: "settingsHotspot" },
    ]},
];

// Toggle states (persisted via command daemon)
MaschineMK3.settingsAutoUpdate = false;
MaschineMK3.settingsTailscale  = false;
MaschineMK3.settingsHotspot    = false;
```

- [ ] **Step 2: Add helper to find next/prev selectable item index**

Add after the tab definitions:

```javascript
// Returns the index of the next selectable item in the given direction.
// Wraps around. Returns current if no selectable items exist.
MaschineMK3.settingsNextSelectable = function(tab, current, direction) {
    var items = MaschineMK3.settingsTabs[tab].items;
    var len = items.length;
    if (len === 0) { return 0; }
    var idx = current;
    for (var i = 0; i < len; i++) {
        idx = (idx + direction + len) % len;
        if (items[idx].type !== "info") { return idx; }
    }
    return current;
};

// Returns the index of the first selectable item in a tab.
MaschineMK3.settingsFirstSelectable = function(tab) {
    var items = MaschineMK3.settingsTabs[tab].items;
    for (var i = 0; i < items.length; i++) {
        if (items[i].type !== "info") { return i; }
    }
    return 0;
};
```

- [ ] **Step 3: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(settings): add tab data model and cursor helpers"
```

---

### Task 2: Skin Attributes and QSS Styles

**Files:**
- Modify: `skin/MK3/skin.xml:10-24` (manifest attributes)
- Modify: `skin/MK3/style.qss` (append new styles)

Add all skin COs needed by the settings panel and the QSS styles for the new widget types.

- [ ] **Step 1: Add skin attributes for settings panel COs**

In `skin/MK3/skin.xml`, replace the existing `show_settings` attribute line and add the full set. After the `show_t9` line, replace:

```xml
      <attribute config_key="[Skin],show_settings">0</attribute>
```

with:

```xml
      <attribute config_key="[Skin],show_settings">0</attribute>
      <attribute config_key="[Skin],settings_tab_0">1</attribute>
      <attribute config_key="[Skin],settings_tab_1">0</attribute>
      <attribute config_key="[Skin],settings_tab_2">0</attribute>
      <attribute config_key="[Skin],settings_cursor_0">1</attribute>
      <attribute config_key="[Skin],settings_cursor_1">0</attribute>
      <attribute config_key="[Skin],settings_cursor_2">0</attribute>
      <attribute config_key="[Skin],settings_cursor_3">0</attribute>
      <attribute config_key="[Skin],settings_cursor_4">0</attribute>
      <attribute config_key="[Skin],settings_cursor_5">0</attribute>
      <attribute config_key="[Skin],settings_confirming">0</attribute>
      <attribute config_key="[Skin],settings_autoupdate">0</attribute>
      <attribute config_key="[Skin],settings_tailscale">0</attribute>
      <attribute config_key="[Skin],settings_hotspot">0</attribute>
```

- [ ] **Step 2: Add QSS styles for settings panel**

Append to `skin/MK3/style.qss`:

```css
/* ── Settings Panel ─────────────────────────────────────── */

#SettingsPanel {
    background-color: #0d0d1a;
}

#SettingsTabBar {
    background-color: #111122;
}

#SettingsTabActive {
    font-size: 11px;
    font-weight: bold;
    color: #e67e22;
    qproperty-alignment: AlignCenter;
    background-color: #1a1a2e;
    border-bottom: 2px solid #e67e22;
    padding: 4px;
}

#SettingsTabInactive {
    font-size: 11px;
    color: #555555;
    qproperty-alignment: AlignCenter;
    background-color: #111122;
    border-bottom: 2px solid #111122;
    padding: 4px;
}

#SettingsItem {
    font-size: 12px;
    color: #aaaaaa;
    qproperty-alignment: AlignLeft|AlignVCenter;
    padding: 2px 12px;
    background-color: #0d0d1a;
}

#SettingsItemHighlight {
    font-size: 12px;
    color: #ffffff;
    qproperty-alignment: AlignLeft|AlignVCenter;
    padding: 2px 12px;
    background-color: #1a1a2e;
    border-left: 3px solid #e67e22;
}

#SettingsItemInfo {
    font-size: 12px;
    color: #555555;
    qproperty-alignment: AlignLeft|AlignVCenter;
    padding: 2px 12px;
    background-color: #0d0d1a;
}

#SettingsChevron {
    font-size: 14px;
    color: #555555;
    qproperty-alignment: AlignRight|AlignVCenter;
    padding: 2px 12px;
}

#SettingsChevronHighlight {
    font-size: 14px;
    color: #e67e22;
    qproperty-alignment: AlignRight|AlignVCenter;
    padding: 2px 12px;
}

#SettingsToggleOn {
    font-size: 10px;
    font-weight: bold;
    color: #ffffff;
    qproperty-alignment: AlignCenter;
    background-color: #e67e22;
    border-radius: 7px;
    padding: 1px 6px;
}

#SettingsToggleOff {
    font-size: 10px;
    color: #888888;
    qproperty-alignment: AlignCenter;
    background-color: #333333;
    border-radius: 7px;
    padding: 1px 6px;
}

#SettingsConfirm {
    font-size: 12px;
    font-weight: bold;
    color: #e74c3c;
    qproperty-alignment: AlignLeft|AlignVCenter;
    padding: 2px 12px;
    background-color: #2a1a1a;
    border-left: 3px solid #e74c3c;
}
```

- [ ] **Step 3: Commit**

```bash
git add skin/MK3/skin.xml skin/MK3/style.qss
git commit -m "feat(settings): add skin COs and QSS styles for tabbed panel"
```

---

### Task 3: Settings Panel Skin XML — Tab Bar and Tab Content

**Files:**
- Modify: `skin/MK3/skin.xml:444-508` (replace existing settings panel)

Replace the placeholder settings panel with the full tabbed layout. Each tab is a `WidgetGroup` whose visibility is bound to its tab CO. Each item row has a highlighted and normal variant bound to cursor COs.

- [ ] **Step 1: Replace the settings panel in skin.xml**

Remove everything between `<!-- ═══════ SETTINGS PANEL (480x272) ═══════ -->` and `<!-- ═══════ PAD INFO: LOOPS (480x272) ═══════ -->` (lines 444-508), and replace with:

```xml
    <!-- ═══════ SETTINGS PANEL (480x272) ═══════ -->
    <WidgetGroup>
      <ObjectName>SettingsPanel</ObjectName>
      <Size>480,272</Size>
      <SizePolicy>f,f</SizePolicy>
      <Layout>vertical</Layout>
      <Connection>
        <ConfigKey>[Skin],show_settings</ConfigKey>
        <BindProperty>visible</BindProperty>
      </Connection>
      <Children>

        <!-- Tab bar: 4 equal columns aligned to D buttons -->
        <WidgetGroup>
          <ObjectName>SettingsTabBar</ObjectName>
          <Size>480,28</Size>
          <SizePolicy>f,f</SizePolicy>
          <Layout>horizontal</Layout>
          <Children>
            <!-- Tab 0: General -->
            <WidgetGroup><Size>120,28</Size><SizePolicy>f,f</SizePolicy><Children>
              <Label><ObjectName>SettingsTabActive</ObjectName><Size>120,28</Size><Text>GENERAL</Text>
                <Connection><ConfigKey>[Skin],settings_tab_0</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
              <Label><ObjectName>SettingsTabInactive</ObjectName><Size>120,28</Size><Text>GENERAL</Text>
                <Connection><ConfigKey>[Skin],settings_tab_0</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection></Label>
            </Children></WidgetGroup>
            <!-- Tab 1: Library -->
            <WidgetGroup><Size>120,28</Size><SizePolicy>f,f</SizePolicy><Children>
              <Label><ObjectName>SettingsTabActive</ObjectName><Size>120,28</Size><Text>LIBRARY</Text>
                <Connection><ConfigKey>[Skin],settings_tab_1</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
              <Label><ObjectName>SettingsTabInactive</ObjectName><Size>120,28</Size><Text>LIBRARY</Text>
                <Connection><ConfigKey>[Skin],settings_tab_1</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection></Label>
            </Children></WidgetGroup>
            <!-- Tab 2: Network -->
            <WidgetGroup><Size>120,28</Size><SizePolicy>f,f</SizePolicy><Children>
              <Label><ObjectName>SettingsTabActive</ObjectName><Size>120,28</Size><Text>NETWORK</Text>
                <Connection><ConfigKey>[Skin],settings_tab_2</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
              <Label><ObjectName>SettingsTabInactive</ObjectName><Size>120,28</Size><Text>NETWORK</Text>
                <Connection><ConfigKey>[Skin],settings_tab_2</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection></Label>
            </Children></WidgetGroup>
            <!-- Tab 3: empty (D4/D8 position) -->
            <WidgetGroup><Size>120,28</Size><SizePolicy>f,f</SizePolicy><Children></Children></WidgetGroup>
          </Children>
        </WidgetGroup>

        <!-- ── GENERAL TAB CONTENT ──────────────────────────── -->
        <WidgetGroup>
          <SizePolicy>me,me</SizePolicy>
          <Layout>vertical</Layout>
          <Connection><ConfigKey>[Skin],settings_tab_0</ConfigKey><BindProperty>visible</BindProperty></Connection>
          <Children>
            <!-- Item 0: Reboot (action, confirm) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <!-- Normal -->
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_0</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Reboot</Text></Label>
                  <Label><ObjectName>SettingsChevron</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
              <!-- Highlighted -->
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_0</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <!-- Normal highlight (not confirming) -->
                  <WidgetGroup><SizePolicy>me,f</SizePolicy><Layout>horizontal</Layout>
                    <Connection><ConfigKey>[Skin],settings_confirming</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                    <Children>
                      <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Reboot</Text></Label>
                      <Label><ObjectName>SettingsChevronHighlight</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                    </Children>
                  </WidgetGroup>
                  <!-- Confirming -->
                  <Label><ObjectName>SettingsConfirm</ObjectName><Size>480,38</Size><Text>Are you sure? Push to confirm</Text>
                    <Connection><ConfigKey>[Skin],settings_confirming</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>

            <!-- Item 1: Shutdown (action, confirm) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_1</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Shutdown</Text></Label>
                  <Label><ObjectName>SettingsChevron</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_1</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <WidgetGroup><SizePolicy>me,f</SizePolicy><Layout>horizontal</Layout>
                    <Connection><ConfigKey>[Skin],settings_confirming</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                    <Children>
                      <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Shutdown</Text></Label>
                      <Label><ObjectName>SettingsChevronHighlight</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                    </Children>
                  </WidgetGroup>
                  <Label><ObjectName>SettingsConfirm</ObjectName><Size>480,38</Size><Text>Are you sure? Push to confirm</Text>
                    <Connection><ConfigKey>[Skin],settings_confirming</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>

            <!-- Item 2: Check for Updates (action) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_2</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Check for Updates</Text></Label>
                  <Label><ObjectName>SettingsChevron</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_2</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Check for Updates</Text></Label>
                  <Label><ObjectName>SettingsChevronHighlight</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>

            <!-- Item 3: Auto-update on boot (toggle) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_3</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Auto-update on boot</Text></Label>
                  <Label><ObjectName>SettingsToggleOn</ObjectName><Size>50,38</Size><Text>ON</Text>
                    <Connection><ConfigKey>[Skin],settings_autoupdate</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
                  <Label><ObjectName>SettingsToggleOff</ObjectName><Size>50,38</Size><Text>OFF</Text>
                    <Connection><ConfigKey>[Skin],settings_autoupdate</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection></Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_3</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Auto-update on boot</Text></Label>
                  <Label><ObjectName>SettingsToggleOn</ObjectName><Size>50,38</Size><Text>ON</Text>
                    <Connection><ConfigKey>[Skin],settings_autoupdate</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
                  <Label><ObjectName>SettingsToggleOff</ObjectName><Size>50,38</Size><Text>OFF</Text>
                    <Connection><ConfigKey>[Skin],settings_autoupdate</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>

            <!-- Item 4: Version (info) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
              <Children>
                <Label><ObjectName>SettingsItemInfo</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Version</Text></Label>
              </Children>
            </WidgetGroup>
          </Children>
        </WidgetGroup>

        <!-- ── LIBRARY TAB CONTENT ──────────────────────────── -->
        <WidgetGroup>
          <SizePolicy>me,me</SizePolicy>
          <Layout>vertical</Layout>
          <Connection><ConfigKey>[Skin],settings_tab_1</ConfigKey><BindProperty>visible</BindProperty></Connection>
          <Children>
            <!-- Item 0: Rescan Library (action) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_0</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Rescan Library</Text></Label>
                  <Label><ObjectName>SettingsChevron</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_0</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Rescan Library</Text></Label>
                  <Label><ObjectName>SettingsChevronHighlight</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>

            <!-- Item 1: Mount USB Drive (action) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_1</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Mount USB Drive</Text></Label>
                  <Label><ObjectName>SettingsChevron</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_1</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Mount USB Drive</Text></Label>
                  <Label><ObjectName>SettingsChevronHighlight</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>

            <!-- Item 2: Unmount USB Drive (action) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_2</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Unmount USB Drive</Text></Label>
                  <Label><ObjectName>SettingsChevron</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_2</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Unmount USB Drive</Text></Label>
                  <Label><ObjectName>SettingsChevronHighlight</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>

            <!-- Item 3: Library Location (info) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
              <Children>
                <Label><ObjectName>SettingsItemInfo</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Library Location</Text></Label>
              </Children>
            </WidgetGroup>
          </Children>
        </WidgetGroup>

        <!-- ── NETWORK TAB CONTENT ──────────────────────────── -->
        <WidgetGroup>
          <SizePolicy>me,me</SizePolicy>
          <Layout>vertical</Layout>
          <Connection><ConfigKey>[Skin],settings_tab_2</ConfigKey><BindProperty>visible</BindProperty></Connection>
          <Children>
            <!-- Item 0: IP Address (info) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
              <Children>
                <Label><ObjectName>SettingsItemInfo</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>IP Address</Text></Label>
              </Children>
            </WidgetGroup>

            <!-- Item 1: Hostname (info) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
              <Children>
                <Label><ObjectName>SettingsItemInfo</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Hostname</Text></Label>
              </Children>
            </WidgetGroup>

            <!-- Item 2: WiFi Network (info) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
              <Children>
                <Label><ObjectName>SettingsItemInfo</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>WiFi Network</Text></Label>
              </Children>
            </WidgetGroup>

            <!-- Item 3: WiFi Select (action) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_3</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>WiFi Select</Text></Label>
                  <Label><ObjectName>SettingsChevron</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_3</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>WiFi Select</Text></Label>
                  <Label><ObjectName>SettingsChevronHighlight</ObjectName><Size>40,38</Size><Text>›</Text></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>

            <!-- Item 4: Tailscale (toggle) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_4</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Tailscale</Text></Label>
                  <Label><ObjectName>SettingsToggleOn</ObjectName><Size>50,38</Size><Text>ON</Text>
                    <Connection><ConfigKey>[Skin],settings_tailscale</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
                  <Label><ObjectName>SettingsToggleOff</ObjectName><Size>50,38</Size><Text>OFF</Text>
                    <Connection><ConfigKey>[Skin],settings_tailscale</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection></Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_4</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Tailscale</Text></Label>
                  <Label><ObjectName>SettingsToggleOn</ObjectName><Size>50,38</Size><Text>ON</Text>
                    <Connection><ConfigKey>[Skin],settings_tailscale</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
                  <Label><ObjectName>SettingsToggleOff</ObjectName><Size>50,38</Size><Text>OFF</Text>
                    <Connection><ConfigKey>[Skin],settings_tailscale</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>

            <!-- Item 5: Hotspot (toggle) -->
            <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Children>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_5</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection>
                <Children>
                  <Label><ObjectName>SettingsItem</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Hotspot</Text></Label>
                  <Label><ObjectName>SettingsToggleOn</ObjectName><Size>50,38</Size><Text>ON</Text>
                    <Connection><ConfigKey>[Skin],settings_hotspot</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
                  <Label><ObjectName>SettingsToggleOff</ObjectName><Size>50,38</Size><Text>OFF</Text>
                    <Connection><ConfigKey>[Skin],settings_hotspot</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection></Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup><Size>480,38</Size><SizePolicy>f,f</SizePolicy><Layout>horizontal</Layout>
                <Connection><ConfigKey>[Skin],settings_cursor_5</ConfigKey><BindProperty>visible</BindProperty></Connection>
                <Children>
                  <Label><ObjectName>SettingsItemHighlight</ObjectName><SizePolicy>me,f</SizePolicy><Size>0,38</Size><Text>Hotspot</Text></Label>
                  <Label><ObjectName>SettingsToggleOn</ObjectName><Size>50,38</Size><Text>ON</Text>
                    <Connection><ConfigKey>[Skin],settings_hotspot</ConfigKey><BindProperty>visible</BindProperty></Connection></Label>
                  <Label><ObjectName>SettingsToggleOff</ObjectName><Size>50,38</Size><Text>OFF</Text>
                    <Connection><ConfigKey>[Skin],settings_hotspot</ConfigKey><BindProperty>visible</BindProperty><Transform><Not/></Transform></Connection></Label>
                </Children>
              </WidgetGroup>
            </Children></WidgetGroup>
          </Children>
        </WidgetGroup>

      </Children>
    </WidgetGroup>
```

- [ ] **Step 2: Commit**

```bash
git add skin/MK3/skin.xml
git commit -m "feat(settings): tabbed settings panel skin layout with cursor highlighting"
```

---

### Task 4: JS Settings Panel — Open/Close, Tab Switching, D-Button Repurposing

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js` (onButtonPress, updatePanels, updateSettingsSkinCOs)

This task wires up the settings button toggle, D-button tab switching when settings is open, and the skin CO update function that drives the display.

- [ ] **Step 1: Add updateSettingsSkinCOs function**

Add after the `updatePanels` function (around line 441):

```javascript
// ---------------------------------------------------------------------------
// updateSettingsSkinCOs — push settings state to skin COs for display.
// ---------------------------------------------------------------------------
MaschineMK3.updateSettingsSkinCOs = function() {
    // Tab visibility
    for (var t = 0; t < 3; t++) {
        engine.setValue("[Skin]", "settings_tab_" + t, MaschineMK3.settingsTab === t ? 1 : 0);
    }
    // Cursor position (max 6 items per tab)
    for (var c = 0; c < 6; c++) {
        engine.setValue("[Skin]", "settings_cursor_" + c, MaschineMK3.settingsCursor === c ? 1 : 0);
    }
    // Confirmation mode
    engine.setValue("[Skin]", "settings_confirming", MaschineMK3.settingsConfirm ? 1 : 0);
    // Toggle states
    engine.setValue("[Skin]", "settings_autoupdate", MaschineMK3.settingsAutoUpdate ? 1 : 0);
    engine.setValue("[Skin]", "settings_tailscale", MaschineMK3.settingsTailscale ? 1 : 0);
    engine.setValue("[Skin]", "settings_hotspot", MaschineMK3.settingsHotspot ? 1 : 0);
};
```

- [ ] **Step 2: Add updateSettingsLEDs function**

Add right after `updateSettingsSkinCOs`:

```javascript
// ---------------------------------------------------------------------------
// updateSettingsLEDs — set D-button LEDs for settings tabs.
// Active tab = bright, other tabs = dim, unused D4/D8 = off.
// ---------------------------------------------------------------------------
MaschineMK3.updateSettingsLEDs = function() {
    var offset = (MaschineMK3.activeDeck === 1) ? 5 : 1; // D5-D8 or D1-D4
    for (var i = 0; i < 4; i++) {
        var dName = "d" + (offset + i);
        if (i < 3) {
            MaschineMK3.setLed(dName, MaschineMK3.settingsTab === i ? 63 : 16);
        } else {
            MaschineMK3.setLed(dName, 0);
        }
    }
};
```

- [ ] **Step 3: Update the settings case in onButtonPress to reset state on open**

Replace the existing `case "settings":` block (around line 808-819):

```javascript
    // --- Settings: toggle settings panel ---
    case "settings":
        MaschineMK3.settingsVisible = !MaschineMK3.settingsVisible;
        if (MaschineMK3.settingsVisible) {
            MaschineMK3.libraryVisible = false;
            MaschineMK3.mixerVisible = false;
            MaschineMK3.settingsTab = 0;
            MaschineMK3.settingsCursor = MaschineMK3.settingsFirstSelectable(0);
            MaschineMK3.settingsConfirm = false;
            MaschineMK3.updateSettingsLEDs();
        }
        if (MaschineMK3.padMode === "t9") { MaschineMK3.padMode = null; }
        MaschineMK3.updatePadModeLED();
        MaschineMK3.updatePadLEDs();
        MaschineMK3.updatePanels();
        MaschineMK3.updateSettingsSkinCOs();
        break;
```

- [ ] **Step 4: Repurpose D buttons when settings is open**

In `onButtonPress`, modify each D-button case (d1-d8) to check for settings mode first. Replace the entire D-button block (cases d1 through d8):

```javascript
    // --- D buttons: settings tabs when settings open, else per-deck controls ---
    case "d1": case "d2": case "d3": case "d4":
    case "d5": case "d6": case "d7": case "d8":
        var dNum = parseInt(name.charAt(1), 10);  // 1-8
        if (MaschineMK3.settingsVisible) {
            // D buttons on the settings screen side act as tab selectors
            var settingsOffset = (MaschineMK3.activeDeck === 1) ? 5 : 1;
            var tabIdx = dNum - settingsOffset;
            if (tabIdx >= 0 && tabIdx < 3) {
                MaschineMK3.settingsTab = tabIdx;
                MaschineMK3.settingsCursor = MaschineMK3.settingsFirstSelectable(tabIdx);
                MaschineMK3.settingsConfirm = false;
                MaschineMK3.updateSettingsLEDs();
                MaschineMK3.updateSettingsSkinCOs();
            }
            break;
        }
        // Normal DJ mode D-button behavior
        if (dNum === 1) {
            engine.setValue("[Channel1]", "sync_enabled",
                engine.getValue("[Channel1]", "sync_enabled") ? 0 : 1);
        } else if (dNum === 5) {
            engine.setValue("[Channel2]", "sync_enabled",
                engine.getValue("[Channel2]", "sync_enabled") ? 0 : 1);
        } else if (dNum === 2) {
            engine.setValue("[Channel1]", "rate_temp_down", 1);
        } else if (dNum === 6) {
            engine.setValue("[Channel2]", "rate_temp_down", 1);
        } else if (dNum === 3) {
            engine.setValue("[Channel1]", "rate_temp_up", 1);
        } else if (dNum === 7) {
            engine.setValue("[Channel2]", "rate_temp_up", 1);
        } else if (dNum === 4) {
            engine.setValue("[Channel1]", "pfl", engine.getValue("[Channel1]", "pfl") ? 0 : 1);
        } else if (dNum === 8) {
            engine.setValue("[Channel2]", "pfl", engine.getValue("[Channel2]", "pfl") ? 0 : 1);
        }
        break;
```

- [ ] **Step 5: Update D-button releases to also guard on settings mode**

In `onButtonRelease`, modify the D2/D3/D6/D7 release cases:

```javascript
    // D button releases — tempo nudge (momentary), skip if settings open
    case "d2":
        if (!MaschineMK3.settingsVisible) { engine.setValue("[Channel1]", "rate_temp_down", 0); }
        break;
    case "d3":
        if (!MaschineMK3.settingsVisible) { engine.setValue("[Channel1]", "rate_temp_up", 0); }
        break;
    case "d6":
        if (!MaschineMK3.settingsVisible) { engine.setValue("[Channel2]", "rate_temp_down", 0); }
        break;
    case "d7":
        if (!MaschineMK3.settingsVisible) { engine.setValue("[Channel2]", "rate_temp_up", 0); }
        break;
```

- [ ] **Step 6: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(settings): tab switching via D buttons, skin CO updates, LED feedback"
```

---

### Task 5: JS Settings Panel — Cursor Navigation and Action Execution

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js` (onButtonPress nav cases)

Wire up nav encoder to move cursor and execute actions when settings is open.

- [ ] **Step 1: Guard nav buttons when settings is open**

In `onButtonPress`, replace the navUp/navDown/navPush cases to check for settings mode first:

```javascript
    // --- Navigation (4D encoder) ---
    case "navUp":
        if (MaschineMK3.settingsVisible) {
            MaschineMK3.settingsConfirm = false;
            MaschineMK3.settingsCursor = MaschineMK3.settingsNextSelectable(
                MaschineMK3.settingsTab, MaschineMK3.settingsCursor, -1);
            MaschineMK3.updateSettingsSkinCOs();
        } else {
            engine.setValue("[Library]", "MoveUp", 1);
        }
        break;
    case "navDown":
        if (MaschineMK3.settingsVisible) {
            MaschineMK3.settingsConfirm = false;
            MaschineMK3.settingsCursor = MaschineMK3.settingsNextSelectable(
                MaschineMK3.settingsTab, MaschineMK3.settingsCursor, 1);
            MaschineMK3.updateSettingsSkinCOs();
        } else {
            engine.setValue("[Library]", "MoveDown", 1);
        }
        break;
    case "navLeft":
        if (!MaschineMK3.settingsVisible) {
            engine.setValue("[Library]", "MoveFocusBackward", 1);
        }
        break;
    case "navRight":
        if (!MaschineMK3.settingsVisible) {
            engine.setValue("[Library]", "MoveFocusForward", 1);
        }
        break;
    case "navPush":
        if (MaschineMK3.settingsVisible) {
            MaschineMK3.settingsExecuteItem();
        } else if (MaschineMK3.libraryVisible) {
            // Cycle focus: search bar (1) → track table (3) → load track
            var focus = engine.getValue("[Library]", "focused_widget");
            if (focus === 1) {
                engine.setValue("[Library]", "focused_widget", 3);
            } else {
                engine.setValue("[Channel" + MaschineMK3.activeDeck + "]", "LoadSelectedTrack", 1);
                MaschineMK3.libraryVisible = false;
                MaschineMK3.padMode = null;
                MaschineMK3.updatePadModeLED();
                MaschineMK3.updatePadLEDs();
                MaschineMK3.updatePanels();
            }
        }
        break;
```

- [ ] **Step 2: Add settingsExecuteItem function**

Add after `updateSettingsLEDs`:

```javascript
// ---------------------------------------------------------------------------
// settingsExecuteItem — execute the currently highlighted settings item.
// Handles confirmation for destructive actions, toggles, and command dispatch.
// ---------------------------------------------------------------------------
MaschineMK3.settingsExecuteItem = function() {
    var tab = MaschineMK3.settingsTabs[MaschineMK3.settingsTab];
    var item = tab.items[MaschineMK3.settingsCursor];
    if (!item || item.type === "info") { return; }

    if (item.type === "toggle") {
        // Toggle the state and update skin
        MaschineMK3[item.stateKey] = !MaschineMK3[item.stateKey];
        MaschineMK3.updateSettingsSkinCOs();
        // Dispatch command to daemon
        var cmd = item.action + (MaschineMK3[item.stateKey] ? "-on" : "-off");
        MaschineMK3.settingsDispatchCommand(cmd);
        return;
    }

    // Action type
    if (item.confirm && !MaschineMK3.settingsConfirm) {
        // Enter confirmation mode
        MaschineMK3.settingsConfirm = true;
        MaschineMK3.updateSettingsSkinCOs();
        // Auto-cancel after 5 seconds
        MaschineMK3.settingsConfirmTimer = engine.beginTimer(5000, function() {
            MaschineMK3.settingsConfirm = false;
            MaschineMK3.settingsConfirmTimer = 0;
            MaschineMK3.updateSettingsSkinCOs();
        }, true);
        return;
    }

    // Execute (either confirmed destructive or non-destructive action)
    if (MaschineMK3.settingsConfirmTimer) {
        engine.stopTimer(MaschineMK3.settingsConfirmTimer);
        MaschineMK3.settingsConfirmTimer = 0;
    }
    MaschineMK3.settingsConfirm = false;
    MaschineMK3.updateSettingsSkinCOs();

    // Special case: rescan uses Mixxx built-in CO
    if (item.action === "rescan") {
        engine.setValue("[Library]", "rescan", 1);
        return;
    }

    MaschineMK3.settingsDispatchCommand(item.action);
};
```

- [ ] **Step 3: Add settingsDispatchCommand function**

Add right after `settingsExecuteItem`:

```javascript
// ---------------------------------------------------------------------------
// settingsDispatchCommand — write a command to /tmp/mk3-settings-cmd
// for the background daemon to execute.
// ---------------------------------------------------------------------------
MaschineMK3.settingsDispatchCommand = function(cmd) {
    // Mixxx JS has no file I/O. Use controller.send() to write a marker
    // that the daemon can detect, or use engine.setValue on a custom CO.
    // For now, log the command — the daemon integration is in Task 7.
    print("MK3 Settings command: " + cmd);
};
```

- [ ] **Step 4: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(settings): cursor navigation, action execution, confirmation flow"
```

---

### Task 6: Command Executor Daemon

**Files:**
- Modify: `pi-setup/mk3-settings-watcher.py` (complete rewrite)
- Modify: `pi-setup/mk3-settings-watcher.service`

Repurpose the settings watcher from an HID button reader to a command file watcher. The JS mapping signals commands by writing to a Mixxx CO; the daemon polls a command file at `/tmp/mk3-settings-cmd`.

Since Mixxx JS cannot write files directly, the daemon also watches HID for the settings button state and reads the command from a shared mechanism. The simplest bridge: the JS mapping calls `engine.setValue("[Skin]", "settings_command", N)` where N is a command code. The daemon reads the Xvfb pixel at a known location that changes color based on the command CO — but this is fragile.

Better approach: use a named pipe or the existing T9 daemon pattern. The T9 daemon uses xdotool for input. For settings, we can use a similar approach — the daemon watches a file that gets written by a helper script triggered from Mixxx.

Simplest MVP: the daemon watches `/tmp/mk3-settings-cmd`. A cron-like helper or the T9 daemon writes commands there when triggered by a CO change. For the MVP, we'll write the daemon and test it standalone, then wire up the JS→daemon bridge.

- [ ] **Step 1: Rewrite mk3-settings-watcher.py as command executor**

Replace the entire contents of `pi-setup/mk3-settings-watcher.py`:

```python
#!/usr/bin/env python3
"""MK3 Settings command executor daemon.

Watches /tmp/mk3-settings-cmd for commands written by the Mixxx JS mapping
(via a bridge script) and executes system actions.

Runs as a systemd service alongside Mixxx.
"""
import os
import sys
import subprocess
import time

CMD_FILE = "/tmp/mk3-settings-cmd"
RESULT_FILE = "/tmp/mk3-settings-result"
POLL_INTERVAL = 0.5  # seconds


def execute_command(cmd):
    """Execute a settings command and return a result string."""
    cmd = cmd.strip()
    print(f"mk3-settings: executing '{cmd}'", file=sys.stderr)

    try:
        if cmd == "reboot":
            write_result("Rebooting...")
            subprocess.run(["sudo", "reboot"], check=False)
        elif cmd == "shutdown":
            write_result("Shutting down...")
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
        elif cmd == "update":
            write_result("Updating...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            subprocess.Popen(
                ["sudo", "bash", os.path.join(script_dir, "mk3-update.sh")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif cmd == "mount-usb":
            mount_usb()
        elif cmd == "unmount-usb":
            unmount_usb()
        elif cmd == "tailscale-on":
            subprocess.run(["sudo", "tailscale", "up"], check=False)
            write_result("Tailscale connected")
        elif cmd == "tailscale-off":
            subprocess.run(["sudo", "tailscale", "down"], check=False)
            write_result("Tailscale disconnected")
        elif cmd == "tailscale-setup":
            tailscale_setup()
        elif cmd == "hotspot-on":
            # Future: nmcli or hostapd
            write_result("Hotspot: not yet implemented")
        elif cmd == "hotspot-off":
            write_result("Hotspot: not yet implemented")
        elif cmd == "autoupdate-on":
            set_autoupdate(True)
        elif cmd == "autoupdate-off":
            set_autoupdate(False)
        else:
            write_result(f"Unknown command: {cmd}")
    except Exception as e:
        write_result(f"Error: {e}")


def write_result(msg):
    """Write a result message for the JS mapping to read."""
    try:
        with open(RESULT_FILE, "w") as f:
            f.write(msg + "\n")
    except IOError:
        pass
    print(f"mk3-settings: {msg}", file=sys.stderr)


def mount_usb():
    """Find and mount the first unmounted USB block device."""
    try:
        result = subprocess.run(
            ["lsblk", "-rno", "NAME,TYPE,MOUNTPOINT"],
            capture_output=True, text=True, check=True,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "part":
                name = parts[0]
                mountpoint = parts[2] if len(parts) > 2 else ""
                dev = f"/dev/{name}"
                # Skip root/boot partitions
                if mountpoint in ("/", "/boot", "/boot/firmware"):
                    continue
                if not mountpoint:
                    mount_dir = f"/media/usb-{name}"
                    os.makedirs(mount_dir, exist_ok=True)
                    subprocess.run(["sudo", "mount", dev, mount_dir], check=True)
                    write_result(f"Mounted {dev} at {mount_dir}")
                    return
        write_result("No USB drive found")
    except Exception as e:
        write_result(f"Mount failed: {e}")


def unmount_usb():
    """Unmount any USB drive mounted under /media/usb-*."""
    try:
        import glob as g
        mounts = g.glob("/media/usb-*")
        if not mounts:
            write_result("No USB drive mounted")
            return
        for mount_dir in mounts:
            subprocess.run(["sudo", "umount", mount_dir], check=True)
            os.rmdir(mount_dir)
        write_result("USB drive unmounted")
    except Exception as e:
        write_result(f"Unmount failed: {e}")


def tailscale_setup():
    """Run tailscale up and capture the auth URL for QR display."""
    try:
        proc = subprocess.Popen(
            ["sudo", "tailscale", "up"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in iter(proc.stdout.readline, ""):
            line = line.strip()
            if "https://" in line:
                # Extract URL and generate QR code
                url = line.split()[-1] if line.split() else line
                write_result(f"tailscale-auth:{url}")
                # Render QR to the MK3 screen via a PNG displayed on Xvfb
                display = os.environ.get("DISPLAY", ":99")
                try:
                    subprocess.run(
                        ["qrencode", "-o", "/tmp/mk3-tailscale-qr.png",
                         "-s", "6", "-m", "2", url],
                        check=True,
                    )
                    subprocess.Popen(
                        ["feh", "--fullscreen", "/tmp/mk3-tailscale-qr.png"],
                        env={**os.environ, "DISPLAY": display},
                    )
                except FileNotFoundError:
                    write_result(f"tailscale-auth:{url} (qrencode not installed)")
                break
        proc.wait()
    except Exception as e:
        write_result(f"Tailscale setup failed: {e}")


def set_autoupdate(enabled):
    """Enable or disable auto-update on boot."""
    config_file = "/etc/mk3-autoupdate"
    try:
        if enabled:
            with open(config_file, "w") as f:
                f.write("1\n")
            write_result("Auto-update enabled")
        else:
            if os.path.exists(config_file):
                os.remove(config_file)
            write_result("Auto-update disabled")
    except IOError as e:
        write_result(f"Config error: {e}")


def main():
    print("mk3-settings: daemon started, watching " + CMD_FILE, file=sys.stderr)

    # Clean up stale files
    for f in (CMD_FILE, RESULT_FILE):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass

    while True:
        try:
            if os.path.exists(CMD_FILE):
                with open(CMD_FILE, "r") as f:
                    cmd = f.read().strip()
                os.remove(CMD_FILE)
                if cmd:
                    execute_command(cmd)
        except Exception as e:
            print(f"mk3-settings: error: {e}", file=sys.stderr)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update the systemd service**

Replace `pi-setup/mk3-settings-watcher.service`:

```ini
[Unit]
Description=MK3 Settings Command Executor
After=mixxx.service

[Service]
Type=simple
User=pi
Environment=DISPLAY=:99
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStart=/usr/bin/python3 /home/pi/mixx-mk3/pi-setup/mk3-settings-watcher.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Commit**

```bash
git add pi-setup/mk3-settings-watcher.py pi-setup/mk3-settings-watcher.service
git commit -m "feat(settings): command executor daemon replaces HID watcher"
```

---

### Task 7: JS-to-Daemon Bridge

**Files:**
- Modify: `mapping/Native-Instruments-Maschine-MK3.js` (settingsDispatchCommand)

Mixxx JS cannot write files or exec processes directly. The command executor daemon (Task 6) watches `/tmp/mk3-settings-cmd`, but we need a bridge from JS to that file.

**MVP approach**: The JS `settingsDispatchCommand` logs the command via `print()`. The daemon is fully functional and can be tested standalone (`echo "reboot" > /tmp/mk3-settings-cmd`). The actual JS→daemon bridge will be wired in a follow-up task — likely by extending the T9 daemon (which already runs in the Xvfb context with xdotool) to also poll a `[Skin]` CO and write the command file.

- [ ] **Step 1: Update settingsDispatchCommand with logging and TODO**

Replace the placeholder `settingsDispatchCommand` from Task 5:

```javascript
MaschineMK3.settingsDispatchCommand = function(cmd) {
    // TODO: Wire bridge to mk3-settings-watcher.py daemon.
    // The daemon watches /tmp/mk3-settings-cmd but Mixxx JS cannot write
    // files. Plan: extend T9 daemon to poll [Skin],settings_command CO
    // and write the cmd file. For now, log + manual test:
    //   echo "reboot" > /tmp/mk3-settings-cmd
    print("MK3 Settings command: " + cmd);
};
```

- [ ] **Step 2: Commit**

```bash
git add mapping/Native-Instruments-Maschine-MK3.js
git commit -m "feat(settings): settingsDispatchCommand with TODO for daemon bridge"
```

---

### Task 8: Pi Setup Script — Tailscale Installation

**Files:**
- Modify: `pi-setup/mk3-pi-setup.sh`

Add Tailscale and qrencode installation to the Pi setup script with an optional interactive setup prompt.

- [ ] **Step 1: Add Tailscale and qrencode to apt install**

In `mk3-pi-setup.sh`, add `qrencode` and `feh` to the apt-get install list (line 21-37). Add after `wireplumber`:

```bash
    qrencode \
    feh
```

- [ ] **Step 2: Add Tailscale setup section after step 7 (services)**

Add a new section between step 7 and step 8. Update the step numbers (current 8 becomes 9). Insert after the services section (around line 213):

```bash
# ── 8. Tailscale VPN (optional) ────────────────────────────────────
echo "--- [8/9] Tailscale VPN ---"
if ! command -v tailscale &>/dev/null; then
    echo "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

echo ""
read -p "Set up Tailscale VPN now? (y/n): " TAILSCALE_SETUP
if [ "$TAILSCALE_SETUP" = "y" ] || [ "$TAILSCALE_SETUP" = "Y" ]; then
    echo "Starting Tailscale..."
    echo "A login URL will appear below. Visit it in your browser to authenticate."
    echo ""
    sudo tailscale up
    echo ""
    echo "Tailscale status:"
    tailscale status
else
    echo "Tailscale installed but not configured."
    echo "You can set it up later via Settings > Network > Setup VPN on the MK3."
fi
```

- [ ] **Step 3: Update step numbers**

Change `[8/8]` to `[9/9]` for the verify section. Update the initial echo to say `[1/9]` etc.

- [ ] **Step 4: Commit**

```bash
git add pi-setup/mk3-pi-setup.sh
git commit -m "feat(settings): add Tailscale installation to Pi setup script"
```

---

### Task 9: Deploy and Test on Hardware

**Files:** None (deployment task)

- [ ] **Step 1: Push all changes to remote**

```bash
git push origin feature/t9-input
```

- [ ] **Step 2: Pull and deploy on Pi**

```bash
ssh zeb@mixxx.local "cd ~/mixx-mk3 && git pull --ff-only origin feature/t9-input"
```

- [ ] **Step 3: Copy mapping and skin to Mixxx directories**

```bash
ssh zeb@mixxx.local "cp ~/mixx-mk3/mapping/Native-Instruments-Maschine-MK3.js ~/.mixxx/controllers/ && cp ~/mixx-mk3/mapping/Native-Instruments-Maschine-MK3.hid.xml ~/.mixxx/controllers/ && sudo cp ~/mixx-mk3/skin/MK3/skin.xml /usr/share/mixxx/skins/MK3/ && sudo cp ~/mixx-mk3/skin/MK3/style.qss /usr/share/mixxx/skins/MK3/"
```

- [ ] **Step 4: Restart services**

```bash
ssh zeb@mixxx.local "sudo systemctl daemon-reload && sudo systemctl restart mk3-settings-watcher && sudo systemctl restart mixxx"
```

- [ ] **Step 5: Test on hardware**

Verify:
1. Press Settings button — panel appears on non-active screen with GENERAL tab active
2. Press D buttons (on the settings screen side) — tabs switch
3. Nav Up/Down — cursor moves between selectable items, skips info rows
4. Nav Push on "Reboot" — shows confirmation text "Are you sure? Push to confirm"
5. Nav Up/Down while confirming — cancels confirmation
6. Wait 5s while confirming — auto-cancels
7. Toggle items (Auto-update) — shows ON/OFF state change
8. Settings button again — closes panel, D buttons return to normal DJ function
9. Settings LED: bright when open, dim when closed
10. D button LEDs: active tab bright, others dim when settings open

- [ ] **Step 6: Test command daemon standalone**

```bash
ssh zeb@mixxx.local "echo 'rescan' > /tmp/mk3-settings-cmd && sleep 1 && cat /tmp/mk3-settings-result"
```
