-- test_ui_minimal.lua - 最小UI测试，定位闪退位置
local home = os.getenv("HOME") or os.getenv("USERPROFILE")
local log_path = home .. "/bfd_ui_test.log"
local function tlog(msg)
    local f = io.open(log_path, "a")
    if f then f:write(os.date("%H:%M:%S") .. " " .. tostring(msg) .. "\n"); f:close() end
end

local f = io.open(log_path, "w")
if f then f:write("=== UI最小测试 " .. os.date() .. " ===\n"); f:close() end

tlog("Step 0: Script loaded")

local resolve = bmd.scriptapp("Resolve")
tlog("Step 1: Connected to Resolve: " .. tostring(resolve ~= nil))

local fusion = resolve:Fusion()
tlog("Step 2: Fusion: " .. tostring(fusion ~= nil))

local ui = fusion.UIManager
tlog("Step 3: UIManager: " .. tostring(ui ~= nil))

local disp = bmd.UIDispatcher(ui)
tlog("Step 4: Dispatcher: " .. tostring(disp ~= nil))

-- Create minimal window
local win = disp:AddWindow({
    WindowTitle = "BFD UI Test",
    ID = "TestWin",
    Geometry = { 100, 100, 400, 200 },
    ui:VGroup{
        ui:Label{ ID = "Lbl", Text = "点击按钮测试UI事件" },
        ui:Button{ ID = "BtnTest", Text = "测试按钮" },
        ui:Button{ ID = "BtnClose", Text = "关闭" },
    },
})

tlog("Step 5: Window created: " .. tostring(win ~= nil))

if not win then
    tlog("FATAL: Window creation failed")
    return
end

-- Event handlers
local click_count = 0
win.On.BtnTest.Clicked = function(ev)
    click_count = click_count + 1
    tlog("BtnTest clicked! count=" .. click_count)
    print("[TEST] Button clicked! count=" .. click_count)
end

win.On.BtnClose.Clicked = function(ev)
    tlog("BtnClose clicked, exiting loop...")
    disp:ExitLoop()
    tlog("ExitLoop called")
end

win.On.TestWin.Close = function(ev)
    tlog("Window close event")
    disp:ExitLoop()
end

win:Show()
tlog("Step 6: Window shown, entering RunLoop...")

local ok, err = pcall(function()
    disp:RunLoop()
end)

tlog("Step 7: RunLoop exited: ok=" .. tostring(ok) .. " err=" .. tostring(err))
tlog("=== Test complete ===")
print("\n[BFD UI TEST] 测试完成，结果见: " .. log_path)
