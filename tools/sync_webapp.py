# -*- coding: utf-8 -*-
"""从主 index.html 生成 webapp/index.html（iOS App 用的增强副本）。

全部补丁都是「锚点精确替换 + 幂等」：锚点找不到但目标已在 → 视为已应用跳过；
锚点找不到且目标也不在 → 报错退出（主文件结构变了，需要人工对锚点）。
跑两遍输出必须逐字节一致。

补丁内容：
  1. iOS 壳桥（SHELL 检测 / __ztPencilTap 笔杆双击 / __ztShellFile 导入回灌 / shellSendExport 导出）
  2. 导入按钮三处走原生 UIDocumentPicker 桥
  3. download() 在壳内改走 POST /__zt/export + 系统分享
  4. pdf.js / worker / pdf-lib 优先加载本地 vendor/（离线可用），失败回退 CDN
  5. 书写顺滑化：ink 画布 desynchronized 低延迟提示 + getPredictedEvents 预测墨迹（湿墨尾巴）
  6. selftest 增加壳桥检查
"""
import io, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "index.html")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp", "index.html")

src = io.open(SRC, encoding="utf-8", newline="").read()
EOL = "\r\n" if "\r\n" in src[:3000] else "\n"


def rep(text, old, new, expect=1, tag=""):
    n = text.count(old)
    if n == 0:
        if new in text:
            print("  [skip] %-24s 已应用" % tag)
            return text
        raise SystemExit("[FAIL] %s：锚点不存在且补丁未应用——主 index.html 结构变了，需人工对锚点\n锚点: %r" % (tag, old[:120]))
    if n != expect:
        raise SystemExit("[FAIL] %s：锚点出现 %d 次（预期 %d）" % (tag, n, expect))
    print("  [ok]   %s" % tag)
    return text.replace(old, new, expect)


print("== sync_webapp: EOL=%r ==" % (EOL,))


def bl(block):
    """插入块按源文件 EOL 规范化。"""
    return block.replace("\n", EOL) if EOL != "\n" else block


# ---------- 1. download() 壳内改走导出桥 ----------
src = rep(
    src,
    'function download(name,blob){var a=document.createElement("a");',
    'function download(name,blob){if(SHELL){shellSendExport(name,blob);return}var a=document.createElement("a");',
    tag="download-桥",
)

# ---------- 2. 壳桥主体块（插在「工具切换」注释前） ----------
BRIDGE = """/* ===== iOS 壳桥（仅 App 内生效；桌面浏览器 SHELL=false 行为完全不变）=====
   原生壳注入 __ZT_SHELL=1（document-start user script）并提供 ztBridge 消息通道。
   ?shelltest=1 仅用于无头自动化测试，强制按壳内路径执行。 */
var SHELL=(location.search.indexOf("shelltest=1")>=0)||((typeof __ZT_SHELL!=="undefined")&&__ZT_SHELL===1)||!!(window.webkit&&window.webkit.messageHandlers&&window.webkit.messageHandlers.ztBridge);
function shellImport(kind){
  try{window.webkit.messageHandlers.ztBridge.postMessage({type:"import",kind:kind})}
  catch(e){toast("导入桥不可用："+(e&&e.message||e))}
}
function shellSendExport(name,blob){
  showLoading("正在交给系统保存…");
  fetch("/__zt/export?name="+encodeURIComponent(name),{method:"POST",body:blob}).then(function(r){
    hideLoading();
    if(!r.ok){toast("导出桥失败 HTTP "+r.status);return}
    try{window.webkit.messageHandlers.ztBridge.postMessage({type:"exported",name:name})}catch(e){}
  },function(e){hideLoading();toast("导出桥失败："+(e&&e.message||e))});
}
/* 原生导入回灌：壳把文件放进 /__zt/inbox，这里取回构造 File 走既有导入逻辑 */
window.__ztShellFile=async function(url,name,kind){
  try{
    var r=await fetch(url);if(!r.ok)throw new Error("HTTP "+r.status);
    var buf=await r.arrayBuffer();
    if(kind==="pdf"){
      var f=new File([buf],name,{type:"application/pdf"});
      return loadFile(f);
    }
    var txt="";try{txt=new TextDecoder("utf-8").decode(buf)}catch(err){txt=""}
    if(kind==="bak"){
      var res=applyBackup(txt);
      if(!res.ok){toast(res.msg);return}
      if(!confirm(res.msg+"，恢复将覆盖本机现有数据并刷新页面，继续？"))return;
      toast("恢复完成，正在刷新…",1500);setTimeout(function(){location.reload()},800);
      return;
    }
    /* kind==="vocab"：与生词本导入同款合并逻辑 */
    var obj=null;try{obj=JSON.parse(txt)}catch(err){}
    var incoming=obj&&obj.words?obj.words:Array.isArray(obj)?obj:null;
    if(!incoming){toast("不是有效的生词本 JSON");return}
    var added=0,skip=0;
    incoming.forEach(function(x){
      if(!x||!x.w)return;
      var norm=String(x.w).trim().toLowerCase(),dup=false;
      for(var i=0;i<V.words.length;i++)if((V.words[i].w||"").toLowerCase()===norm){dup=true;break}
      if(dup){skip++;return}
      V.words.unshift({id:"v"+(V.seq++),w:String(x.w).trim(),def:x.def||"",phon:x.phon||"",src:x.src||"导入",mastered:!!x.mastered,created:x.created||Date.now(),page:x.page||null});
      added++;
    });
    saveV();renderVocab();toast("导入完成：新增 "+added+" 个，跳过重复 "+skip+" 个");
  }catch(e){toast("导入失败："+(e&&e.message||e))}
};
/* Apple Pencil 笔杆「轻点两下」：Safari 不转发，App 里由原生 UIPencilInteraction
   按系统设置（设置→Apple Pencil→轻点两下）识别后转发到这里。 */
window.__ztPencilTap=function(action){
  try{
    if(action==="switchEraser"){toggleEraser();return}
    if(action==="switchPrevious"){
      if(prefs.tool==="pen")setTool(lastDrawTool&&lastDrawTool!=="pen"?lastDrawTool:"eraser");
      else setTool("pen");
      toast("已切换到："+(TOOL_NAME[prefs.tool]||prefs.tool));return;
    }
    if(action==="colorPalette"||action==="inkAttributes"){
      toast("系统把「轻点两下」设成了调色/参数，本页未映射；可在 设置→Apple Pencil 改为「切换到橡皮」");return;
    }
  }catch(e){}
};
"""
src = rep(src, "/* ================= 工具切换 ================= */", bl(BRIDGE) + "/* ================= 工具切换 ================= */", tag="壳桥块")

# ---------- 3. 导入按钮三处 ----------
src = rep(src,
          '$("bImport").addEventListener("click",function(){$("file").click()});',
          '$("bImport").addEventListener("click",function(){if(SHELL)shellImport("pdf");else $("file").click()});',
          tag="导入-主")
src = rep(src,
          '$("bImport2").addEventListener("click",function(){$("file").click()});',
          '$("bImport2").addEventListener("click",function(){if(SHELL)shellImport("pdf");else $("file").click()});',
          tag="导入-空态")
src = rep(src,
          '$("vImport").addEventListener("click",function(){$("vFile").click()});',
          '$("vImport").addEventListener("click",function(){if(SHELL)shellImport("vocab");else $("vFile").click()});',
          tag="导入-生词")
src = rep(src,
          '$("mRestore").addEventListener("click",function(){menu.hidden=true;$("bakFile").click()});',
          '$("mRestore").addEventListener("click",function(){menu.hidden=true;if(SHELL)shellImport("bak");else $("bakFile").click()});',
          tag="导入-备份")

# ---------- 4. 离线 vendor 优先 ----------
src = rep(src,
          '  if(!window.pdfjsLib){try{await loadScript(CDN_UNPKG+"/build/pdf.min.js")}catch(e){}}',
          '  if(!window.pdfjsLib){try{await loadScript("vendor/pdf.min.js")}catch(e){}}' + EOL +
          '  if(!window.pdfjsLib){try{await loadScript(CDN_UNPKG+"/build/pdf.min.js")}catch(e){}}',
          tag="vendor-pdfjs")
src = rep(src,
          '  if(!window.PDFLib){try{await loadScript("https://unpkg.com/pdf-lib@1.17.1/dist/pdf-lib.min.js")}catch(e){}}',
          '  if(!window.PDFLib){try{await loadScript("vendor/pdf-lib.min.js")}catch(e){}}' + EOL +
          '  if(!window.PDFLib){try{await loadScript("https://unpkg.com/pdf-lib@1.17.1/dist/pdf-lib.min.js")}catch(e){}}',
          tag="vendor-pdflib")
src = rep(src,
          '  var urls=[WORKER_JSDELIVR,WORKER_UNPKG];',
          '  var urls=["vendor/pdf.worker.min.js",WORKER_JSDELIVR,WORKER_UNPKG];',
          tag="vendor-worker")

# ---------- 5a. （已撤）desynchronized 低延迟画布 ----------
# 2026-10-07 撤：WebKit 对 desynchronized 的实现不透明，App 端实测反馈卡顿后回归保守路线。
# 顺滑化只保留预测墨迹（getPredictedEvents，纯增量、不进数据）。

# ---------- 5b. live 状态加预测字段 ----------
src = rep(src,
          'var live={mode:null,pv:null,pid:null,stroke:null,t0:0,sx:0,sy:0,moved:0};',
          'var live={mode:null,pv:null,pid:null,stroke:null,t0:0,sx:0,sy:0,moved:0,pred:null,predAt:0};',
          tag="live-预测字段")

# ---------- 5c. paintLive 叠预测尾巴 ----------
src = rep(src,
          '  if(live&&live.stroke&&live.pv===pv)drawStroke(pv.ictx,live.stroke);',
          '  if(live&&live.stroke&&live.pv===pv){' + EOL +
          '    drawStroke(pv.ictx,live.stroke);' + EOL +
          '    if(live.pred)drawPredTail(pv); /* 预测墨迹：湿墨尾巴，下一帧被真实笔迹整体替换 */' + EOL +
          '  }',
          tag="paintLive-预测")

# ---------- 5d. 预测捕获（onMove 通用书写分支） ----------
src = rep(src,
          '  schedulePaint(pv);' + EOL +
          '  if((live.mode==="pen"||live.mode==="p")&&prefs.penSub===0)armSnapDwell(pv,e.clientX,e.clientY); /* 增强版：停笔不动→识别规则图形 */',
          '  /* iOS 壳增强：预测采样（getPredictedEvents，iOS 18.2+）——把系统预测的未来轨迹先画出来，' + EOL +
          '     视觉上追回约一帧延迟；每来一个真实事件整条尾巴被替换，不支持时走原路径。 */' + EOL +
          '  if(live.mode==="pen"||live.mode==="hl"){' + EOL +
          '    var pev=null;' + EOL +
          '    if(e.getPredictedEvents){try{pev=e.getPredictedEvents()}catch(err){pev=null}}' + EOL +
          '    live.pred=(pev&&pev.length)?pev:null;' + EOL +
          '    live.predAt=performance.now();' + EOL +
          '    armPredExpiry(pv);' + EOL +
          '  }' + EOL +
          '  schedulePaint(pv);' + EOL +
          '  if((live.mode==="pen"||live.mode==="p")&&prefs.penSub===0)armSnapDwell(pv,e.clientX,e.clientY); /* 增强版：停笔不动→识别规则图形 */',
          tag="onMove-预测捕获")

# ---------- 5e. 预测渲染/过期函数（插在 paintLive 前） ----------
PRED = """/* ===== iOS 壳增强：预测墨迹渲染 =====
   湿墨尾巴只画在合成层、绝不进数据：live.pred 每个真实事件都整体替换，
   compositeInk 重画时旧尾巴自动消失；停笔不再来事件由过期定时器擦掉。 */
var PRED_MAX=36;
function drawPredTail(pv){
  var st=live.stroke,pe=live.pred;
  if(!st||!pe||!pe.length)return;
  var n=st.pts.length;
  var pts=[st.pts[n-3],st.pts[n-2],st.pts[n-1]];
  var used=0;
  for(var i=0;i<pe.length&&used<PRED_MAX;i++){
    var q=pe[i];
    if(q.clientX==null)continue;
    var pt=sp(pv,{clientX:q.clientX,clientY:q.clientY});
    var dx=pt.x-pts[pts.length-3],dy=pt.y-pts[pts.length-2];
    if(used===0&&dx*dx+dy*dy<0.25)continue; /* 跳过贴着真实笔尖的重复预测 */
    if(used===0){dx*=0.6;dy*=0.6}            /* 首点收一点，避免接缝折角 */
    var k=1-(used/PRED_MAX)*0.7;
    pts.push(r1(pts[pts.length-3]+dx),r1(pts[pts.length-2]+dy),r1(Math.max(0.08,st.pts[n-1]*k)));
    used++;
  }
  if(used<1)return;
  drawStroke(pv.ictx,{t:st.t==="h"?"h":"p",c:st.c,w:st.w,pts:pts});
}
var predTimer=0;
function armPredExpiry(pv){
  if(predTimer)return;
  predTimer=setTimeout(function(){
    predTimer=0;
    if(live&&live.pred&&performance.now()-(live.predAt||0)>=55){
      live.pred=null;
      if(live.pv&&live.pv.ictx)paintLive(live.pv);
    }
  },70);
}
"""
src = rep(src, "function paintLive(pv){", bl(PRED) + "function paintLive(pv){", tag="预测函数")

# ---------- 5f. 抬笔/取消清预测 ----------
src = rep(src,
          '  var st=live.stroke;live.mode=null;live.stroke=null;cancelPaint();',
          '  live.pred=null;' + EOL + '  var st=live.stroke;live.mode=null;live.stroke=null;cancelPaint();',
          tag="onUp-清预测")
src = rep(src,
          '  live.mode=null;live.stroke=null;gesture=null;' + EOL + '}',
          '  live.pred=null;live.mode=null;live.stroke=null;gesture=null;' + EOL + '}',
          tag="onCancel-清预测")

# ---------- 6. selftest 增加壳桥检查 ----------
SELFTEST = """  ck("ZT 钩子",!!window.ZT);
  /* iOS 壳桥（桌面也执行：__ztPencilTap 恒定义，切换逻辑与原生转发共用） */
  ck("iOS壳·双击桥",typeof window.__ztPencilTap==="function");
  ck("iOS壳·检测标志",typeof SHELL==="boolean");
  var st0=prefs.tool;
  window.__ztPencilTap("switchEraser");
  var stT1=prefs.tool;
  window.__ztPencilTap("switchEraser");
  var stT2=prefs.tool;
  ck("iOS壳·双击切换",stT1!==st0||stT2!==stT1);
  setTool(st0);"""
src = rep(src, '  ck("ZT 钩子",!!window.ZT);', bl(SELFTEST), tag="selftest-壳桥")

# ---------- 7. ZT 调试钩子：live 状态与墨迹画布统计（供自动化探针；主脚本在 IIFE 内，
#              S/live/pv 对外部不可见——这是本项目探针的既知约束，见开发文档 §五） ----------
ZTHOOKS = """  /* ===== iOS 壳增强：自动化探针钩子 ===== */
  liveState:function(){
    if(!live)return null;
    return{mode:live.mode||null,hasStroke:!!live.stroke,predLen:live.pred?live.pred.length:0,
      predAt:live.predAt||0,moved:Math.round(live.moved||0)};
  },
  inkStats:function(i){
    var pv=S.pageViews[i];if(!pv||!pv.ictx)return null;
    try{
      var d=pv.ictx.getImageData(0,0,pv.ic.width,pv.ic.height).data,n=0,tot=0;
      for(var k=3;k<d.length;k+=64){tot++;if(d[k]>40)n++}
      return{w:pv.ic.width,h:pv.ic.height,nonBlank:n,tot:tot};
    }catch(e){return{err:String(e)}}
  },"""
src = rep(src,
          '  penSub:function(v){if(v===undefined)return prefs.penSub;prefs.penSub=v;savePrefs();renderPenShapeRow();return prefs.penSub},',
          bl(ZTHOOKS) + EOL + '  penSub:function(v){if(v===undefined)return prefs.penSub;prefs.penSub=v;savePrefs();renderPenShapeRow();return prefs.penSub},',
          tag="ZT-探针钩子")

# ---------- 输出 ----------
os.makedirs(os.path.dirname(OUT), exist_ok=True)
io.open(OUT, "w", encoding="utf-8", newline="").write(src)
print("written:", os.path.normpath(OUT), len(src), "bytes")
