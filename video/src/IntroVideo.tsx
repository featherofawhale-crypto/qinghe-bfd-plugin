import { useCurrentFrame, spring, interpolate, AbsoluteFill, Sequence, Audio, staticFile } from "remotion";
import React from "react";

const BG = "#000000";
const WHITE = "#f5f5f7";
const ACCENT = "#0071e3";
const GRAY = "#86868b";
const DARK = "#1d1d1f";
const GOLD = "#ffd60a";
const FONT = "Helvetica Neue, Helvetica, Arial, PingFang SC, Microsoft YaHei, sans-serif";
// 4K大字体 - 手机也能看清

const Fade = ({ children, start = 0, dur = 25 }: any) => {
  const f = useCurrentFrame();
  return <div style={{ opacity: interpolate(f, [start, start + dur], [0, 1], { extrapolateRight: "clamp" }) }}>{children}</div>;
};
const Up = ({ children, start = 0, dur = 25, dist = 30 }: any) => {
  const f = useCurrentFrame();
  const p = spring({ frame: f - start, fps: 30, config: { damping: 20, stiffness: 80 } });
  return <div style={{ opacity: interpolate(f, [start, start + 10], [0, 1], { extrapolateRight: "clamp" }), transform: `translateY(${interpolate(p, [0, 1], [dist, 0])}px)` }}>{children}</div>;
};

const S1_Title = () => (
  <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center" }}>
    <Audio src={staticFile("bfd_chime.m4a")} startFrom={30} />
    <Fade start={15}><div style={{ color: GRAY, fontSize: 60, letterSpacing: 12, textTransform: "uppercase", fontFamily: FONT, fontWeight: 300 }}>DaVinci Resolve</div></Fade>
    <div style={{ height: 40 }} />
    <Fade start={35}><h1 style={{ color: WHITE, fontSize: 200, fontWeight: 700, margin: 0, letterSpacing: -3, fontFamily: FONT }}>黑帧夹帧检测</h1></Fade>
    <Up start={65} dist={30}><p style={{ color: GRAY, fontSize: 64, fontWeight: 300, marginTop: 20, fontFamily: FONT }}>自动扫描时间线 · 精准定位问题 · 一键标记修复</p></Up>
    <Up start={90} dist={20}><p style={{ color: ACCENT, fontSize: 76, fontWeight: 500, marginTop: 100, fontFamily: FONT }}>清何 · v1.9.44</p></Up>
  </AbsoluteFill>
);

const S2_Problems = () => (
  <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center", padding: "0 300px" }}>
    <Up start={5}><h2 style={{ color: WHITE, fontSize: 160, fontWeight: 700, margin: 0, textAlign: "center", fontFamily: FONT }}>剪辑中，你是否遇到过这些？</h2></Up>
    <div style={{ marginTop: 120, display: "flex", flexDirection: "column", gap: 48, width: "100%" }}>
      {["成片导出后才发现黑帧，全部重来","重复镜头混在时间线里找不到","调色后镜头被隐藏，合成出 Bug","手动排查耗时数小时，眼睛都花"].map((t, i) => (
        <Up key={i} start={25 + i * 22} dist={20}>
          <div style={{ background: DARK, borderRadius: 36, padding: "56px 72px", display: "flex", alignItems: "center", gap: 36 }}>
            <div style={{ width: 72, height: 72, borderRadius: "50%", background: ACCENT, display: "flex", alignItems: "center", justifyContent: "center", color: WHITE, fontSize: 60, fontWeight: 700, flexShrink: 0, fontFamily: FONT }}>!</div>
            <span style={{ color: WHITE, fontSize: 52, fontFamily: FONT }}>{t}</span>
          </div>
        </Up>
      ))}
    </div>
  </AbsoluteFill>
);

const S3_Features = () => (
  <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center", padding: "0 200px" }}>
    <Up start={5}><h2 style={{ color: WHITE, fontSize: 160, fontWeight: 700, margin: 0, textAlign: "center", fontFamily: FONT }}>9 种检测，一条时间线全搞定</h2></Up>
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 36, marginTop: 100, width: "100%" }}>
      {[
        ["⬛","黑帧检测","FFmpeg 高精度分析画面全黑"],
        ["✂️","夹帧检测","≤ 3 帧极短异常片段识别"],
        ["🔄","路径重复","同一文件相同片段多次使用"],
        ["🎨","帧指纹重复","跨文件 + 调色后画面比对"],
        ["👁️","透明度检测","隐藏 / 低透明度 / 禁用素材"],
        ["📐","叠加夹帧","多轨道遮挡时可见性计算"],
        ["🟣","空位检测","片段间隙定位，容差 2 帧"],
        ["🔵","转场识别","正常转场黑幕与异常区分"],
        ["🚀","复杂模式","渲染后合成画面全量分析"],
      ].map(([e, t, d], i) => (
        <Up key={i} start={25 + i * 12} dist={12}>
          <div style={{ background: DARK, borderRadius: 36, padding: "60px 56px", textAlign: "center" }}>
            <div style={{ fontSize: 80, marginBottom: 16 }}>{e}</div>
            <div style={{ color: WHITE, fontSize: 76, fontWeight: 600, fontFamily: FONT }}>{t}</div>
            <div style={{ color: GRAY, fontSize: 60, marginTop: 12, fontFamily: FONT }}>{d}</div>
          </div>
        </Up>
      ))}
    </div>
  </AbsoluteFill>
);

const S4_Colors = () => (
  <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center" }}>
    <Up start={5}><h2 style={{ color: WHITE, fontSize: 160, fontWeight: 700, margin: 0, textAlign: "center", fontFamily: FONT }}>彩色标记，问题一目了然</h2></Up>
    <Up start={20}><p style={{ color: GRAY, fontSize: 52, marginTop: 16, fontFamily: FONT }}>13 种颜色覆盖所有问题类型</p></Up>
    <div style={{ marginTop: 80, display: "flex", flexDirection: "column", gap: 6 }}>
      {[
        ["#ff3b30","Red","夹帧错误 — 极短异常，必须修复"],
        ["#ffd60a","Yellow","可疑黑帧 / 半透明遮挡"],
        ["#007aff","Blue","场景转场 — 正常切换"],
        ["#af52de","Purple","时间线空位 — 片段间隙"],
        ["#ff6b9d","Rose","近距重复 — 间距 < 2 秒，高嫌疑"],
        ["#e8c98b","Sand","远距重复 — 间距 < 2 分钟，需确认"],
        ["#ff2dab","Fuchsia","内容重复 — 跨文件画面匹配"],
        ["#64d2ff","Mint","隐藏素材 — 不透明度 = 0"],
        ["#c9a063","Cocoa","低透明度 — 不透明度 < 50%"],
        ["#ac8eec","Lavender","部分透明 — 不透明度 50-99%"],
        ["#32d74b","Green","非标准合成模式"],
        ["#5ac8fa","Cyan","已禁用素材 / 远距复用"],
        ["#ff375f","Pink","叠加夹帧 — 被上层完全遮挡"],
      ].map(([c, n, d], i) => (
        <Up key={i} start={35 + i * 8} dist={6}>
          <div style={{ display: "flex", alignItems: "center", gap: 36, padding: "12px 0" }}>
            <div style={{ width: 36, height: 36, borderRadius: "50%", backgroundColor: c, boxShadow: `0 0 12px ${c}`, flexShrink: 0 }} />
            <span style={{ color: WHITE, fontSize: 60, fontWeight: 500, width: 200, fontFamily: FONT }}>{n}</span>
            <span style={{ color: GRAY, fontSize: 60, fontFamily: FONT }}>{d}</span>
          </div>
        </Up>
      ))}
    </div>
  </AbsoluteFill>
);

const S5_HowTo = () => {
  const steps = [["1","打开达芬奇","工作区 → 脚本 →\n清何黑帧夹帧检测"],["2","配置参数","选择时间线和灵敏度\n勾选需要的检测类型"],["3","开始检测","点击按钮自动扫描\n数秒内完成全部分析"],["4","查看修复","彩色标记 + 结果面板\n按 ; 键逐个跳转"]];
  return (
    <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center" }}>
      <Up start={5}><h2 style={{ color: WHITE, fontSize: 160, fontWeight: 700, margin: 0, fontFamily: FONT }}>只需 4 步，像喝水一样简单</h2></Up>
      <div style={{ display: "flex", gap: 0, marginTop: 120 }}>
        {steps.map(([n, t, d], i) => (
          <React.Fragment key={i}>
            <Up start={30 + i * 22} dist={15}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 400 }}>
                <div style={{ width: 160, height: 160, borderRadius: "50%", background: ACCENT, display: "flex", alignItems: "center", justifyContent: "center", color: WHITE, fontSize: 160, fontWeight: 700, marginBottom: 24, fontFamily: FONT }}>{n}</div>
                <div style={{ color: WHITE, fontSize: 52, fontWeight: 600, textAlign: "center", fontFamily: FONT }}>{t}</div>
                <div style={{ color: GRAY, fontSize: 60, textAlign: "center", marginTop: 12, lineHeight: 1.8, whiteSpace: "pre-line", fontFamily: FONT }}>{d}</div>
              </div>
            </Up>
            {i < 3 && <div style={{ width: 120, borderTop: "1px solid #333", marginTop: 80 }} />}
          </React.Fragment>
        ))}
      </div>
    </AbsoluteFill>
  );
};

const S6_Modes = () => (
  <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center", padding: "0 250px" }}>
    <Up start={5}><h2 style={{ color: WHITE, fontSize: 160, fontWeight: 700, margin: 0, textAlign: "center", fontFamily: FONT }}>两种模式，覆盖全部场景</h2></Up>
    <div style={{ display: "flex", gap: 80, marginTop: 100 }}>
      <Up start={25} dist={20}>
        <div style={{ background: DARK, borderRadius: 40, padding: "72px 80px", width: 700 }}>
          <div style={{ color: ACCENT, fontSize: 64, fontWeight: 700, marginBottom: 20, fontFamily: FONT }}>普通模式</div>
          <div style={{ color: GRAY, fontSize: 64, marginBottom: 28, fontFamily: FONT }}>日常剪辑检查</div>
          {["逐文件黑帧分析","成片模式（一次分析，更快）","路径重复 + 跨文件帧指纹","透明度 / 合成模式检测"].map((t, i) => (<div key={i} style={{ color: WHITE, fontSize: 64, marginBottom: 10, fontFamily: FONT }}>  {t}</div>))}
        </div>
      </Up>
      <Up start={45} dist={20}>
        <div style={{ background: "#0a1628", borderRadius: 40, padding: "72px 80px", width: 700, border: "2px solid #1a3050" }}>
          <div style={{ color: GOLD, fontSize: 64, fontWeight: 700, marginBottom: 20, fontFamily: FONT }}>复杂模式</div>
          <div style={{ color: GRAY, fontSize: 64, marginBottom: 28, fontFamily: FONT }}>成片终检 · 交付前最后防线</div>
          {["渲染 IO 范围 → 合成后画面","FFmpeg blackdetect 黑帧","场景检测抓夹帧（闪现画面）","渲染文件帧指纹（最准确）"].map((t, i) => (<div key={i} style={{ color: WHITE, fontSize: 64, marginBottom: 10, fontFamily: FONT }}>  {t}</div>))}
        </div>
      </Up>
    </div>
  </AbsoluteFill>
);

const S7_Scenes = () => (
  <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center", padding: "0 250px" }}>
    <Up start={5}><h2 style={{ color: WHITE, fontSize: 160, fontWeight: 700, margin: 0, fontFamily: FONT }}>不同场景，智能适配</h2></Up>
    <Up start={20}><p style={{ color: GRAY, fontSize: 50, marginTop: 16, fontFamily: FONT }}>插件根据时间线结构自动选择最优策略</p></Up>
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48, marginTop: 100, width: "100%" }}>
      {[["🎬","多机位剪辑","同一素材切到多机位，路径重复逐一找出；多轨叠加后底层露出几帧，叠加检测捕获"],["🎨","调色后导出","原始和调色版是两个文件，帧指纹跨文件比对画面内容"],["✅","成片终检","复杂模式渲染所有轨道 + 特效 + 调色后的最终画面，做全套分析"],["📐","多轨合成","扫描每层轨道的透明度和合成模式，发现隐藏素材和忘启用的图层"]].map(([e, t, d], i) => (
        <Up key={i} start={35 + i * 20} dist={15}>
          <div style={{ background: DARK, borderRadius: 40, padding: "64px 72px" }}>
            <div style={{ fontSize: 52, marginBottom: 16 }}>{e}</div>
            <div style={{ color: WHITE, fontSize: 56, fontWeight: 600, marginBottom: 12, fontFamily: FONT }}>{t}</div>
            <div style={{ color: GRAY, fontSize: 60, lineHeight: 1.8, fontFamily: FONT }}>{d}</div>
          </div>
        </Up>
      ))}
    </div>
  </AbsoluteFill>
);

const S8_Outro = () => (
  <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center" }}>
    <Audio src={staticFile("bfd_chime.m4a")} startFrom={15} />
    <Fade start={15}><h1 style={{ color: WHITE, fontSize: 160, fontWeight: 700, margin: 0, letterSpacing: -2, textAlign: "center", lineHeight: 1.3, fontFamily: FONT }}>让机器帮你<br />检查每一个帧</h1></Fade>
    <Up start={55}><p style={{ color: GRAY, fontSize: 64, marginTop: 36, fontFamily: FONT }}>清何黑帧夹帧检测 · v1.9.44</p></Up>
    <Up start={75}><p style={{ color: ACCENT, fontSize: 76, marginTop: 56, fontFamily: FONT }}>达芬奇 工作区 → 脚本 → 一键运行</p></Up>
    <Fade start={105}><div style={{ position: "absolute", bottom: 80, width: "100%", textAlign: "center" }}><p style={{ color: "#555", fontSize: 60, fontFamily: FONT }}>兼容 DaVinci Resolve 17 / 18 / 19 / 20 · macOS</p></div></Fade>
  </AbsoluteFill>
);

export const IntroVideo: React.FC = () => (
  <div style={{ flex: 1, backgroundColor: BG }}>
    <Audio src={staticFile("bfd_bg_music.m4a")} volume={0.8} />
    <Sequence from={0} durationInFrames={140}><S1_Title /></Sequence>
    <Sequence from={140} durationInFrames={160}><S2_Problems /></Sequence>
    <Sequence from={300} durationInFrames={190}><S3_Features /></Sequence>
    <Sequence from={490} durationInFrames={210}><S4_Colors /></Sequence>
    <Sequence from={700} durationInFrames={180}><S5_HowTo /></Sequence>
    <Sequence from={880} durationInFrames={180}><S6_Modes /></Sequence>
    <Sequence from={1060} durationInFrames={190}><S7_Scenes /></Sequence>
    <Sequence from={1250} durationInFrames={210}><S8_Outro /></Sequence>
  </div>
);
