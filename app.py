"""提篮桥人才储备中心 —— 本地档案调阅 UI（Streamlit）。

布局参考 jobs.hanzilla.co：无侧栏，顶部搜索 + 分类浏览 + 分节清单 + FAQ；
视觉延续复古机关档案卷宗（红头文件 × 牛皮纸 × 朱砂印章），全本地字体栈。
页尾「值班用印台」为 components.html 内嵌互动小件（点击盖章动效）。
启动：双击 start_ui.bat（或 streamlit run app.py）
"""

from __future__ import annotations

import html as H
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as components_html

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from jobaggregator.config import load_config          # noqa: E402
from jobaggregator.db import Database                 # noqa: E402
from jobaggregator.paths import LOCK_PATH             # noqa: E402

PLATFORM_NAMES = {"liepin": "猎聘", "job51": "前程无忧",
                  "zhaopin": "智联招聘", "zhipin": "BOSS直聘"}
DOT_CLASS = {"ok": "ok", "empty": "warn", "auth_failed": "err", "error": "err"}
FRESH_OPTIONS = ["全部", "今天", "近3天", "近7天", "近14天", "近30天"]
FRESH_DAYS = {"全部": None, "今天": 1, "近3天": 3, "近7天": 7,
              "近14天": 14, "近30天": 30}
ORDER_OPTIONS = {"最近抓到": "last_seen", "最新发现": "new_first",
                 "薪资从高到低": "salary"}
TEASER_ROWS = 5          # 总目页每个方向先示 5 份

cfg = load_config(ROOT / "config.yaml")
PAGE_SIZE = int(cfg.ui.get("page_size", 30))
YEAR = datetime.now().year

st.set_page_config(page_title="提篮桥人才储备中心", page_icon="📜",
                   layout="wide")


# ---------- 样式：档案卷宗 ----------

CSS = """
<style>
:root{
  --paper:#F4EDDD; --paper2:#FCF8EC; --paper3:#FFFDF4;
  --ink:#211C15; --ink2:#6E6350; --line:#D6C9AC;
  --red:#AE3B2A; --red2:#8C2B1E; --green:#48644A; --amber:#9A7420;
  --serif:'Noto Serif SC','Source Han Serif SC','Songti SC','STSong','SimSun',
          Georgia,'Times New Roman',serif;
  --kai:'KaiTi','STKaiti','楷体','Noto Serif SC','SimSun',serif;
  --mono:Consolas,'Courier New',monospace;
}
.stApp{
  background:
    radial-gradient(1100px 480px at 78% -8%, rgba(174,59,42,.055), transparent 62%),
    repeating-linear-gradient(0deg, transparent 0 31px, rgba(33,28,21,.028) 31px 32px),
    var(--paper);
  color:var(--ink); font-family:var(--serif);
}
#MainMenu, [data-testid="stToolbar"]{visibility:hidden;}
header[data-testid="stHeader"]{background:transparent;}
footer{visibility:hidden; height:0;}
section.main{padding-top:1.1rem; padding-bottom:0;}
p, span, li, label{font-family:var(--serif); color:var(--ink);}
label{font-size:11.5px; color:var(--ink2); letter-spacing:.14em;}
.masthead, .card, .pills, .ledger, .xtra, .cat, .feat, .faq-wrap,
.foot{font-family:var(--serif);}

/* ---- 卷首（红头） ---- */
.masthead{
  position:relative; border:1px solid var(--line); background:var(--paper2);
  padding:16px 28px 14px; margin-bottom:14px;
  box-shadow:inset 0 1px 0 #fff, 0 2px 12px rgba(72,60,32,.10);
  animation:fu .5s ease both;
}
.mh-top{display:flex; justify-content:space-between;
  font-family:var(--mono); font-size:12px; color:var(--ink2); letter-spacing:.06em;}
.mh-title{
  text-align:center; font-size:clamp(25px,3.2vw,38px); font-weight:700;
  letter-spacing:.32em; text-indent:.32em; margin:12px 0 3px;
}
.mh-sub{text-align:center; font-family:var(--kai); color:var(--red);
  font-size:15px; letter-spacing:.42em; text-indent:.42em; margin-bottom:2px;}
.mh-latin{text-align:center; font-family:Georgia,serif; font-style:italic;
  font-size:11px; color:var(--ink2); letter-spacing:.3em; margin-bottom:10px;}
.mh-rule{height:6px; border-top:3px solid var(--red); border-bottom:1px solid var(--ink);}
.mh-meta{display:flex; flex-wrap:wrap; justify-content:center; gap:.6em 2.4em;
  margin-top:10px; font-family:var(--mono); font-size:12px; color:var(--ink2);}
.mh-meta b{color:var(--ink); font-weight:600;}
.seal{
  position:absolute; right:30px; top:44px; width:88px; height:88px;
  border:3px solid rgba(174,59,42,.82); color:rgba(174,59,42,.88);
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  transform:rotate(-8deg); pointer-events:none; user-select:none;
}
.seal::before{content:'★'; font-size:11px; line-height:1; margin-bottom:2px;}
.seal-grid{display:grid; grid-template-columns:repeat(2,1fr); gap:0 6px;
  font-size:23px; font-weight:700; line-height:1.15; text-align:center;}
@media (max-width:860px){ .seal{display:none;} }

/* ---- 顶部搜索台 ---- */
.hero{margin-bottom:2px;}
[data-testid="stTextInput"] div[data-baseweb="input"]{
  border:1px solid var(--ink); border-radius:0; background:var(--paper3);
  box-shadow:3px 3px 0 rgba(33,28,21,.10); transition:all .15s;
}
[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within{
  border-color:var(--red); box-shadow:3px 3px 0 rgba(174,59,42,.30);
}
[data-testid="stTextInput"] input{
  font-family:var(--serif); font-size:16px; color:var(--ink);
}
[data-testid="stTextInput"] input::placeholder{
  color:var(--ink2); opacity:.75; font-family:var(--kai); letter-spacing:.08em;
}

/* ---- 特色条 + 平台状态 ---- */
.feat{display:flex; flex-wrap:wrap; gap:8px 30px; padding:10px 4px 2px;
  font-size:13px; color:var(--ink);}
.feat .fi{display:inline-flex; align-items:baseline; gap:7px;}
.feat .fi::before{content:'❧'; color:var(--red); font-size:14px;}
.feat .fi b{font-weight:700;}
.feat .fi span{font-family:var(--kai); color:var(--ink2); font-size:12.5px;}
.pills{display:flex; flex-wrap:wrap; gap:8px 22px; padding:6px 4px 10px;
  font-family:var(--mono); font-size:12px; color:var(--ink2);
  border-bottom:1px dashed var(--line); margin-bottom:12px;}
.pill{display:inline-flex; align-items:center; gap:7px; white-space:nowrap;}
.dot{width:8px; height:8px; border-radius:50%; display:inline-block;}
.dot.ok{background:var(--green);} .dot.warn{background:var(--amber);}
.dot.err{background:var(--red);}
.pill .lock{color:var(--red); font-weight:700;}

/* ---- 分类卡（方向浏览，卡片下方配「调阅」按钮） ---- */
.cat{
  position:relative; border:1px solid var(--ink);
  background:var(--paper2); padding:12px 14px 10px; margin-bottom:6px;
  animation:fu .45s ease both;
}
.cat .cn{font-weight:700; font-size:14px; letter-spacing:.1em;}
.cat .cnum{font-size:27px; font-weight:700; margin-top:4px;
  font-variant-numeric:tabular-nums;}
.cat .cnum small{font-size:12px; font-weight:400; color:var(--ink2);
  letter-spacing:.15em;}

/* ---- 检索工具行（紧凑小件）：圈住带滑杆的那一行 ---- */
div[data-testid="stHorizontalBlock"]:has([data-testid="stSlider"]){
  border:1px dashed var(--line); background:rgba(252,248,236,.6);
  padding:10px 14px 2px; margin-bottom:14px;
}
div[data-testid="stHorizontalBlock"]:has([data-testid="stSlider"])
  div[data-baseweb="select"]>div{
  border-radius:0!important; border-color:var(--ink)!important;
  background:var(--paper2); font-family:var(--serif);
}
div[data-testid="stHorizontalBlock"]:has([data-testid="stSlider"])
  div[data-baseweb="select"]>div>div{font-size:13px;}
div[data-testid="stHorizontalBlock"]:has([data-testid="stSlider"])
  div.react-aria-ComboBox{
  border:1px solid var(--ink)!important; border-radius:0!important;
  background:var(--paper2);
}
div[data-testid="stHorizontalBlock"]:has([data-testid="stSlider"])
  div.react-aria-ComboBox input{font-family:var(--serif); font-size:13px;
  color:var(--ink); background:transparent;}
div[data-testid="stHorizontalBlock"]:has([data-testid="stSlider"])
  [data-testid="stSlider"]{padding-top:0;}

/* ---- 指标卡 ---- */
.cards{display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-bottom:14px;}
.card{
  position:relative; border:1px solid var(--line); background:var(--paper2);
  padding:13px 18px 11px; animation:fu .5s ease both;
}
.card:nth-child(2){animation-delay:.08s} .card:nth-child(3){animation-delay:.16s}
.card::before{content:''; position:absolute; left:-1px; top:12px; width:4px; height:26px;
  background:var(--red);}
.card .num{font-size:32px; font-weight:700; line-height:1.15;
  font-variant-numeric:tabular-nums;}
.card .lab{font-size:12px; color:var(--ink2); letter-spacing:.3em; margin-top:1px;}

/* ---- 分类卡旧网格样式已并入上方 ---- */

/* ---- 卷宗清单（分节） ---- */
.ledger{border:1px solid var(--ink); background:var(--paper2);
  box-shadow:4px 4px 0 rgba(33,28,21,.10); margin-bottom:20px;}
.ledger-head{display:flex; justify-content:space-between; align-items:baseline;
  gap:12px; padding:10px 18px; border-bottom:1px solid var(--ink);
  background:rgba(33,28,21,.045); flex-wrap:wrap;}
.lh-t{font-weight:700; font-size:15.5px; letter-spacing:.3em;}
.lh-t::before{content:'▍'; color:var(--red); margin-right:6px;}
.lh-c{font-family:var(--mono); font-size:12px; color:var(--ink2);}
.lh-c a{color:var(--red); text-decoration:none; letter-spacing:.08em;
  border-bottom:1px dashed rgba(174,59,42,.5); white-space:nowrap;}
.lh-c a:hover{border-bottom-style:solid;}

details.entry{border-bottom:1px dashed var(--line); animation:fu .45s ease both;}
details.entry:last-of-type{border-bottom:none;}
details.entry>summary{list-style:none; display:block; cursor:pointer;}
details.entry>summary::-webkit-details-marker{display:none;}
.row{
  display:grid; grid-template-columns:52px minmax(0,1fr) 118px 92px;
  gap:12px; padding:10px 18px 11px; align-items:baseline; transition:background .14s;
}
summary:hover .row, details.entry[open] .row{background:var(--paper3);
  box-shadow:inset 3px 0 0 var(--red);}
.no{font-family:var(--mono); font-size:12px; color:var(--ink2);}
.t{font-size:15.5px; font-weight:700; line-height:1.45;}
.t a{color:var(--ink); text-decoration:none;
  border-bottom:1px solid rgba(33,28,21,.28); transition:border-color .14s;}
.t a:hover{border-bottom-color:var(--red);}
.stamp{
  display:inline-block; border:1.5px solid var(--red); color:var(--red);
  font-size:11px; font-weight:700; line-height:1; padding:2px 4px;
  transform:rotate(-6deg) translateY(-1px); margin-right:7px; user-select:none;
}
.meta{font-size:12.5px; color:var(--ink2); margin-top:3px; letter-spacing:.02em;}
.meta .sep{margin:0 6px; color:var(--line);}
.ptag{border:1px solid var(--ink2); padding:0 5px; font-size:11.5px;
  color:var(--ink); white-space:nowrap;}
.sal{font-family:var(--mono); font-size:14px; font-weight:700; color:var(--red2);
  white-space:nowrap; justify-self:end;}
.sal.off{color:var(--ink2); font-weight:400;}
.dt{font-family:var(--mono); font-size:11.5px; color:var(--ink2);
  text-align:right; white-space:nowrap;}
.dt i{font-style:normal; display:block; font-size:10px; letter-spacing:.15em;
  color:var(--line); margin-bottom:1px;}
.hint{font-family:var(--mono); font-size:11px; color:var(--ink2);
  text-align:center; padding:4px 0 10px; letter-spacing:.1em;}

/* ---- 展开详情 ---- */
.xtra{padding:13px 20px 16px 82px; background:rgba(174,59,42,.035);
  border-top:1px dotted var(--line); font-size:13.5px; animation:fu .3s ease both;}
.xtra .xt-head{display:flex; flex-wrap:wrap; gap:10px 26px; margin-bottom:8px;}
.xtra .xt-head b{font-weight:700;}
.xtra .xt-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr));
  gap:4px 30px; color:var(--ink2); font-size:12.5px; margin-bottom:10px;}
.xtra .xt-grid b{color:var(--ink); font-weight:600; margin-right:6px;}
.tags{display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px;}
.tag{border:1px solid var(--line); background:var(--paper3); color:var(--ink2);
  font-size:11.5px; padding:2px 8px;}
.orig{
  display:inline-block; border:1px solid var(--ink); color:var(--ink);
  padding:6px 18px; font-size:13px; letter-spacing:.3em; text-indent:.3em;
  text-decoration:none; transition:all .16s;
}
.orig:hover{background:var(--ink); color:var(--paper2);}

/* ---- 常见问答 ---- */
.faq-wrap{margin:26px 0 6px;}
.faq-cap{font-weight:700; font-size:15.5px; letter-spacing:.3em; margin-bottom:10px;}
.faq-cap::before{content:'▍'; color:var(--red); margin-right:6px;}
details.faq{border:1px solid var(--line); background:var(--paper2); margin-bottom:7px;}
details.faq>summary{list-style:none; cursor:pointer; padding:9px 16px;
  font-weight:700; font-size:13.5px; letter-spacing:.05em;}
details.faq>summary::-webkit-details-marker{display:none;}
details.faq>summary::before{content:'问　'; font-family:var(--kai);
  color:var(--red); font-weight:400;}
details.faq[open]>summary{border-bottom:1px dotted var(--line);}
details.faq .ans{padding:9px 18px 11px 44px; font-family:var(--kai);
  color:var(--ink2); font-size:13px; line-height:1.75;}
details.faq .ans::before{content:'答　'; color:var(--ink);}

/* ---- 空卷宗 / 分页 / 页脚 ---- */
.empty{text-align:center; padding:56px 0 62px;}
.empty .big{font-size:120px; font-weight:700; color:rgba(33,28,21,.07); line-height:1;}
.empty p{margin:14px 0 0; color:var(--ink2); font-family:var(--kai);
  letter-spacing:.2em; font-size:15px;}
.pagenum{font-family:var(--mono); font-size:12.5px; color:var(--ink2);
  letter-spacing:.2em;}
.foot{margin-top:22px; border-top:1px solid var(--ink); padding-top:9px;
  text-align:center;}
.foot .k{font-family:var(--kai); color:var(--ink2); font-size:13.5px;
  letter-spacing:.12em;}
.foot .m{font-family:var(--mono); font-size:11px; color:var(--ink2);
  letter-spacing:.18em; margin-top:4px;}

/* ---- 按钮（快捷签 / 调阅 / 翻卷，统一签风） ---- */
.stButton>button, .stDownloadButton>button{
  font-family:var(--serif); border-radius:0; letter-spacing:.14em;
  border:1px solid var(--ink); color:var(--ink); background:transparent;
  font-size:13px; padding:5px 8px; transition:all .16s;
}
.stButton>button:hover, .stDownloadButton>button:hover{
  border-color:var(--red); color:var(--red); background:rgba(174,59,42,.06);
}
.stButton>button[kind="primary"]{
  background:var(--ink)!important; color:var(--paper2)!important;
  border:1px solid var(--ink); box-shadow:3px 3px 0 rgba(174,59,42,.85);
}
.stButton>button[kind="primary"]:hover{
  transform:translate(-1px,-1px); box-shadow:4px 4px 0 rgba(174,59,42,.95);
}
.stButton>button[kind="primary"]:active{transform:translate(1px,1px); box-shadow:1px 1px 0 rgba(174,59,42,.9);}

@keyframes fu{from{opacity:0; transform:translateY(10px);} to{opacity:1; transform:none;}}
@keyframes stamp{
  0%{opacity:0; transform:rotate(-8deg) scale(1.9);}
  62%{opacity:1; transform:rotate(-8deg) scale(.92);}
  100%{transform:rotate(-8deg) scale(1);}
}
.seal{animation:stamp .5s cubic-bezier(.2,1.4,.4,1) .55s both;}
@media (prefers-reduced-motion: reduce){
  *{animation:none!important; transition:none!important;}
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------- 值班用印台（内嵌互动：点击盖章动效） ----------

DESK_HTML = """
<!doctype html><html><head><meta charset="utf-8"><style>
:root{
  --paper:#F4EDDD; --paper2:#FCF8EC; --ink:#211C15; --ink2:#6E6350;
  --line:#D6C9AC; --red:#AE3B2A;
  --serif:'Noto Serif SC','Source Han Serif SC','Songti SC','SimSun',serif;
  --kai:'KaiTi','STKaiti','楷体','SimSun',serif;
  --mono:Consolas,monospace;
}
html,body{margin:0; background:#F4EDDD; font-family:var(--serif); color:var(--ink);}
.desk{border:1px solid var(--ink); background:var(--paper2); margin:10px 0 6px;
  box-shadow:4px 4px 0 rgba(33,28,21,.10);}
.desk-bar{display:flex; justify-content:space-between; align-items:center;
  padding:8px 16px; border-bottom:1px solid var(--ink);
  background:rgba(33,28,21,.045); font-size:13.5px; font-weight:700;
  letter-spacing:.3em;}
.desk-bar::before{content:'▍'; color:var(--red); margin-right:6px;}
.desk-bar .cnt{font-family:var(--mono); font-size:11.5px; font-weight:400;
  color:var(--ink2); letter-spacing:.12em;}
.paper{position:relative; height:158px; margin:12px 16px; cursor:pointer;
  background:
    repeating-linear-gradient(0deg, transparent 0 27px, rgba(33,28,21,.05) 27px 28px),
    var(--paper);
  border:1px solid var(--line); overflow:hidden;}
.paper .opinion{position:absolute; left:14px; bottom:9px;
  font-family:var(--kai); font-size:12.5px; color:var(--ink2);
  letter-spacing:.1em;}
.mark{position:absolute; border:2px solid rgba(174,59,42,.72);
  color:rgba(174,59,42,.88); font-family:var(--kai); font-size:21px;
  font-weight:700; letter-spacing:.28em; padding:3px 6px 3px 10px;
  mix-blend-mode:multiply; user-select:none; white-space:nowrap;
  transform:rotate(var(--r));
  animation:st .38s cubic-bezier(.2,1.4,.4,1) both;}
@keyframes st{
  0%{opacity:0; transform:rotate(var(--r)) scale(2.2);}
  60%{opacity:1; transform:rotate(var(--r)) scale(.93);}
  100%{transform:rotate(var(--r)) scale(1);}
}
.paper.shake{animation:sk .22s ease;}
@keyframes sk{25%{transform:translate(1px,1px);}50%{transform:translate(-1px,0);}
  75%{transform:translate(1px,0);}}
.tools{display:flex; gap:10px; align-items:center; padding:0 16px 13px;}
.tools button{font-family:var(--serif); font-size:12.5px; letter-spacing:.25em;
  text-indent:.25em; border:1px solid var(--ink); background:transparent;
  color:var(--ink); padding:6px 16px; cursor:pointer; transition:all .15s;}
.tools button:hover{background:var(--red); border-color:var(--red);
  color:var(--paper2);}
.tools #stampBtn{background:var(--red); border-color:var(--red);
  color:#FCF8EC; box-shadow:2px 2px 0 rgba(33,28,21,.5);}
.tools #stampBtn:hover{transform:translate(-1px,-1px);
  box-shadow:3px 3px 0 rgba(33,28,21,.55);}
.tools #stampBtn:active{transform:translate(1px,1px);
  box-shadow:0 0 0 rgba(33,28,21,.5);}
.tools .note{font-family:var(--kai); font-size:12px; color:var(--ink2);
  letter-spacing:.08em; margin-left:auto;}
</style></head><body>
<div class="desk">
  <div class="desk-bar"><span>值班室 · 用印登记</span>
    <span class="cnt" id="cnt">今日用印 0 次</span></div>
  <div class="paper" id="paper" title="点纸面或按「用印」盖章">
    <span class="opinion" id="lastop">待批文件一宗 —— 点击盖章</span>
  </div>
  <div class="tools">
    <button id="stampBtn">⁂ 用 印</button>
    <button id="clearBtn">清 台</button>
    <span class="note">闲来无事的点击动效，也当给求职的自己盖个章</span>
  </div>
</div>
<script>
(function(){
  var ops=['阅','拟同意','情况属实','同意报批','予以存档','缓议','再议',
           '知悉','收到','呈阅','转人事科','妥'];
  var paper=document.getElementById('paper');
  var cnt=document.getElementById('cnt');
  var lastop=document.getElementById('lastop');
  var n=0;
  function stamp(){
    var op=ops[Math.floor(Math.random()*ops.length)];
    var m=document.createElement('span');
    m.className='mark'; m.textContent=op;
    m.style.left=(6+Math.random()*66)+'%';
    m.style.top=(8+Math.random()*52)+'%';
    m.style.setProperty('--r',(-12+Math.random()*24).toFixed(1)+'deg');
    paper.appendChild(m);
    n++;
    cnt.textContent='今日用印 '+n+' 次';
    var t=new Date();
    var hh=('0'+t.getHours()).slice(-2)+':'+('0'+t.getMinutes()).slice(-2);
    lastop.textContent='已批「'+op+'」 · 值班员留痕 '+hh;
    paper.classList.remove('shake');
    void paper.offsetWidth;
    paper.classList.add('shake');
  }
  document.getElementById('stampBtn').addEventListener('click',stamp);
  paper.addEventListener('click',stamp);
  document.getElementById('clearBtn').addEventListener('click',function(){
    Array.prototype.forEach.call(
      paper.querySelectorAll('.mark'),function(e){e.remove();});
    n=0; cnt.textContent='今日用印 0 次';
    lastop.textContent='台面已清 —— 待批文件一宗';
  });
})();
</script></body></html>
"""


# ---------- 工具 ----------

def esc(x) -> str:
    return H.escape(str(x if x is not None else ""))


def fmt_time(s: str) -> str:
    try:
        return datetime.fromisoformat(s).strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return (s or "")[:16].replace("T", " ")


def short_d(s: str) -> str:
    return (s or "")[5:10]


def parse_tags(t):
    if isinstance(t, list):
        return [str(x) for x in t]
    if isinstance(t, str) and t.strip().startswith("["):
        try:
            return [str(x) for x in json.loads(t)]
        except ValueError:
            pass
    return []


# ---------- URL 参数（兼容旧收藏链接的 ?chip=；点击交互一律走按钮回调） ----------

qp = st.query_params
chip = qp.get("chip", "")
if qp:
    qp.clear()
if chip == "today":
    st.session_state["fresh_key"] = "今天"
    st.session_state["order_key"] = "最新发现"
    st.session_state.pop("page", None)
elif chip == "high":
    st.session_state["salary_key"] = 20
    st.session_state.pop("page", None)
elif chip == "intern":
    st.session_state["type_key"] = "实习"
    st.session_state.pop("page", None)
elif chip == "reset":
    for k in ("platform_key", "group_key", "type_key", "fresh_key",
              "salary_key", "search_key", "order_key", "page", "group_sel"):
        st.session_state.pop(k, None)

enabled_platforms = [n for n, p in cfg.platforms.items() if p.enabled]
all_groups = [g.name for g in cfg.keyword_groups]
group_sel = st.session_state.get("group_sel", "")
if group_sel not in all_groups:
    group_sel = ""
default_fresh = next((k for k, v in FRESH_DAYS.items()
                      if v == cfg.ui.get("default_fresh_days")), "近14天")


# ---------- 数据查询（先于首屏指标） ----------

db = Database()
try:
    stats = db.stats()
    run_status = db.latest_status_by_platform()
finally:
    db.close()

today = datetime.now().strftime("%Y-%m-%d")
last_fetch = ""
if run_status:
    last_fetch = fmt_time(max(v["started_at"] for v in run_status.values()))


# ---------- 卷首（红头） ----------

dossier = f"档案编号 沪提储字〔{YEAR}〕第 {stats.get('active_total') or 0:05d} 号"
st.markdown(f"""
<div class="masthead">
  <div class="mh-top"><span>{esc(dossier)}</span><span>内部资料 · 妥善保存</span></div>
  <div class="mh-title">提篮桥人才储备中心</div>
  <div class="mh-sub">长期接收 · 分类归档 · 择日调阅</div>
  <div class="mh-latin">TILANQIAO HUMAN RESERVE ARCHIVE</div>
  <div class="mh-rule"></div>
  <div class="mh-meta">
    <span>收录城市 <b>{esc(cfg.city)}</b></span>
    <span>岗位方向 <b>财务</b></span>
    <span>上次收卷 <b>{esc(last_fetch or "暂无")}</b></span>
  </div>
  <div class="seal"><div class="seal-grid"><span>人</span><span>才</span>
  <span>储</span><span>备</span></div></div>
</div>
""", unsafe_allow_html=True)


# ---------- 顶部搜索台 + 收卷 ----------

hc1, hc2 = st.columns([3.1, 1])
with hc1:
    f_search = st.text_input(
        "关键词", key="search_key", label_visibility="collapsed",
        placeholder="检索档案：输入职位 / 公司关键词，空格分隔多个词…")
with hc2:
    fetching = LOCK_PATH.exists()
    if st.button("立即收卷", type="primary", disabled=fetching,
                 use_container_width=True):
        exe = Path(sys.executable)
        pythonw = exe.with_name("pythonw.exe")
        cmd = str(pythonw if pythonw.exists() else exe)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen([cmd, "run_fetch.py"], cwd=str(ROOT), creationflags=flags)
        st.toast("收卷已启动，一两分钟后刷新页面查看", icon="📄")
        st.rerun()
    if fetching:
        st.caption("收卷进行中……完成后自动解锁")


# ---------- 特色条 + 平台状态 ----------

st.markdown(f"""
<div class="feat">
  <span class="fi"><b>每日 09:30 自动收卷</b><span>无需值守，开机自动补跑</span></span>
  <span class="fi"><b>点职位标题直达原文</b><span>本中心不代收简历</span></span>
  <span class="fi"><b>{esc(cfg.city)} · 财务方向</b><span>五类卷宗分类归档</span></span>
</div>
""", unsafe_allow_html=True)

if run_status:
    pills = []
    for name in enabled_platforms:
        s = run_status.get(name)
        if not s:
            pills.append(f'<span class="pill"><i class="dot"></i>'
                         f'{esc(PLATFORM_NAMES.get(name, name))} 未抓取</span>')
            continue
        t = fmt_time(s["started_at"])
        cls = DOT_CLASS.get(s["status"], "")
        lock = ' <b class="lock">需重登</b>' if s["status"] == "auth_failed" else ""
        tip = esc((s.get("error_text") or "")[:160])
        pills.append(f'<span class="pill" title="{tip}">'
                     f'<i class="dot {cls}"></i>{esc(PLATFORM_NAMES.get(name, name))}'
                     f'{lock}<span>· {esc(t)}</span></span>')
    st.markdown(f'<div class="pills">{"".join(pills)}</div>',
                unsafe_allow_html=True)


# ---------- 快捷签（按钮回调，无需整页重载） ----------


def _chip_today() -> None:
    st.session_state["fresh_key"] = "今天"
    st.session_state["order_key"] = "最新发现"
    st.session_state.pop("page", None)


def _chip_high() -> None:
    st.session_state["salary_key"] = 20
    st.session_state.pop("page", None)


def _chip_intern() -> None:
    st.session_state["type_key"] = "实习"
    st.session_state.pop("page", None)


def _chip_reset() -> None:
    # 不能只 pop：前端控件会保留旧值不回落，必须显式赋回默认
    st.session_state["fresh_key"] = default_fresh
    st.session_state["order_key"] = "最近抓到"
    st.session_state["type_key"] = "全部"
    st.session_state["salary_key"] = 0
    st.session_state["search_key"] = ""
    st.session_state["platform_key"] = enabled_platforms
    st.session_state.pop("page", None)
    st.session_state["group_sel"] = ""


def _back_overview() -> None:
    st.session_state["group_sel"] = ""
    st.session_state.pop("page", None)


chip_specs = [("今日新收录", _chip_today), ("月薪 ≥ 20K", _chip_high),
              ("实习岗位", _chip_intern), ("重置条件", _chip_reset)]
if group_sel:
    chip_specs = [("← 返回总目", _back_overview)] + chip_specs
chip_specs.append(("⟳ 重载", None))
cw = st.columns([1.05] * len(chip_specs))
for col, (label, cb) in zip(cw, chip_specs):
    with col:
        st.button(label, on_click=cb, use_container_width=True)


# ---------- 检索工具行 ----------

with st.container(border=False):
    t1, t2, t3, t4, t5, t6 = st.columns([0.95, 0.72, 1.05, 0.95, 0.62, 1.35])
    with t1:
        f_fresh = st.selectbox("新鲜度", FRESH_OPTIONS,
                               index=FRESH_OPTIONS.index(default_fresh),
                               key="fresh_key", label_visibility="collapsed")
    with t2:
        f_job_type = st.selectbox("性质", ["全部", "全职", "实习"],
                                  key="type_key", label_visibility="collapsed")
    with t3:
        f_salary = st.slider("月薪下限（K）", 0, 60, 0, step=1, key="salary_key")
    with t4:
        f_order = st.selectbox("排序", list(ORDER_OPTIONS), key="order_key",
                               label_visibility="collapsed")
    with t5:
        f_active_only = st.checkbox("只看在招", value=True, key="active_key")
    with t6:
        f_platforms = st.multiselect(
            "档案来源", enabled_platforms, default=enabled_platforms,
            format_func=lambda n: PLATFORM_NAMES.get(n, n), key="platform_key",
            label_visibility="collapsed")

filters = {
    "platforms": f_platforms or None,
    "groups": [group_sel] if group_sel else None,
    "job_type": "" if f_job_type == "全部" else f_job_type,
    "fresh_days": FRESH_DAYS[f_fresh],
    "salary_min_k": float(f_salary) if f_salary > 0 else None,
    "search": f_search.strip(),
    "include_archived": not f_active_only,
    "order": ORDER_OPTIONS[f_order],
    "limit": 1000,
}

db = Database()
try:
    rows = db.query_jobs(**filters)
    counts = db.count_by_group(
        platforms=filters["platforms"], job_type=filters["job_type"],
        fresh_days=filters["fresh_days"], salary_min_k=filters["salary_min_k"],
        search=filters["search"],
        include_archived=filters["include_archived"])
finally:
    db.close()


# ---------- 指标卡 ----------

c1, c2, c3 = st.columns(3)
c1.markdown(f'<div class="card"><div class="num">{stats.get("active_total") or 0}'
            f'</div><div class="lab">在档岗位</div></div>', unsafe_allow_html=True)
c2.markdown(f'<div class="card"><div class="num">{stats.get("today_new") or 0}'
            f'</div><div class="lab">今日新收录</div></div>', unsafe_allow_html=True)
c3.markdown(f'<div class="card"><div class="num">{stats.get("companies") or 0}'
            f'</div><div class="lab">涉及单位</div></div>', unsafe_allow_html=True)


# ---------- 行渲染 ----------

def row_html(no: int, j: dict) -> str:
    new = ('<span class="stamp">新</span>'
           if (j["first_seen_at"] or "")[:10] == today else "")
    sal = j["salary_text"] or "面议"
    sal_cls = "" if j["salary_text"] else "off"
    meta_bits = [
        f'<span>{esc(j["company"] or "")}</span>',
        f'<span class="ptag">{esc(PLATFORM_NAMES.get(j["platform"], j["platform"]))}</span>',
        f'<span>{esc((j["city"] or "") + "-" + (j["district"] or "")).rstrip("-")}</span>',
    ]
    for x in (j["experience"], j["education"]):
        if x:
            meta_bits.append(f'<span>{esc(x)}</span>')
    meta = '<span class="sep">·</span>'.join(meta_bits)
    fs = (j["first_seen_at"] or "").replace("T", " ")[:16]
    ls = (j["last_seen_at"] or "").replace("T", " ")[:16]
    tags = parse_tags(j.get("tags"))
    tags_html = (f'<div class="tags">{"".join(f"<span class=tag>{esc(t)}</span>" for t in tags[:12])}</div>'
                 if tags else "")
    mid = (((j["salary_min_k"] or 0) + (j["salary_max_k"] or 0)) / 2
           if j["salary_min_k"] or j["salary_max_k"] else None)
    mid_txt = f"{mid:.1f}K" if mid else "-"
    delay = min(no * 28, 640)
    return f"""
<details class="entry" style="animation-delay:{delay}ms">
 <summary><div class="row">
  <div class="no">{no:04d}</div>
  <div>
    <div class="t">{new}<a href="{esc(j["url"])}" target="_blank"
      rel="noopener" onclick="event.stopPropagation()">{esc(j["title"])}</a></div>
    <div class="meta">{meta}</div>
  </div>
  <div class="sal {sal_cls}">{esc(sal)}</div>
  <div class="dt"><i>归档</i>{esc(short_d(j["first_seen_at"]))}</div>
 </div></summary>
 <div class="xtra">
   <div class="xt-head">
     <span><b>薪资</b>　{esc(sal)}（约 {mid_txt}）</span>
     <span><b>经验</b>　{esc(j["experience"] or "-")}</span>
     <span><b>学历</b>　{esc(j["education"] or "-")}</span>
   </div>
   <div class="xt-grid">
     <span><b>单位</b>{esc(j["company"] or "")}</span>
     <span><b>行业</b>{esc(j["company_industry"] or "-")}</span>
     <span><b>规模</b>{esc(j["company_size"] or "-")}</span>
     <span><b>联系人</b>{esc(j["hr_name"] or "-")}</span>
     <span><b>方向</b>{esc(j["keyword_group"] or "-")}（{esc(j["job_type"] or "-")}）</span>
     <span><b>发布</b>{esc(j["publish_time_text"] or "-")}</span>
     <span><b>首次发现</b>{esc(fs)}</span>
     <span><b>最近抓到</b>{esc(ls)}</span>
   </div>
   {tags_html}
   <a class="orig" href="{esc(j["url"])}" target="_blank" rel="noopener">调阅原文 ↗</a>
 </div>
</details>"""


# ---------- 正文：总目（分类浏览）或单卷（分页清单） ----------

if group_sel:
    # —— 单卷模式：某方向的完整清单 ——
    total_pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
    page = min(st.session_state.get("page", 0), total_pages - 1)
    st.session_state["page"] = page
    page_rows = rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    st.markdown(f"""
    <div class="ledger">
     <div class="ledger-head">
       <span class="lh-t">{esc(group_sel)}</span>
       <span class="lh-c">共 {counts.get(group_sel, len(rows))} 份 · 按{esc(f_order)}
         · 第 {page + 1}/{total_pages} 卷 · 每卷 {PAGE_SIZE} 份</span>
     </div>
     {"".join(row_html(page * PAGE_SIZE + i + 1, j) for i, j in enumerate(page_rows)) if page_rows
      else '<div class="empty"><div class="big">空</div><p>本卷暂无符合条件的档案 —— 放宽条件，或先「立即收卷」。</p></div>'}
     <div class="hint">点击任一行展开卷内详情 · 职位标题直达原文</div>
    </div>
    """, unsafe_allow_html=True)
else:
    # —— 总目模式：分类卡 + 每方向分节清单 ——
    total_cnt = sum(counts.values())
    if rows or total_cnt == 0:
        cc = st.columns(len(all_groups))
        for i, (col, g) in enumerate(zip(cc, all_groups)):

            def _open_group(name=g) -> None:
                st.session_state["group_sel"] = name
                st.session_state.pop("page", None)

            with col:
                st.markdown(f"""
                <div class="cat" style="animation-delay:{min(i * 60, 360)}ms">
                  <span class="cn">{esc(g)}</span>
                  <span class="cnum">{counts.get(g, 0)}<small> 份在档</small></span>
                </div>""", unsafe_allow_html=True)
                st.button("调阅 →", key=f"cat_{i}", on_click=_open_group,
                          use_container_width=True)
    if rows:
        for g in all_groups:
            n_g = counts.get(g, 0)
            g_rows = [r for r in rows if r["keyword_group"] == g][:TEASER_ROWS]
            if not g_rows and n_g == 0:
                continue
            st.markdown(f"""
            <div class="ledger">
             <div class="ledger-head">
               <span class="lh-t">{esc(g)}</span>
               <span class="lh-c">共 {n_g} 份 · 按{esc(f_order)}</span>
             </div>
             {"".join(row_html(i + 1, j) for i, j in enumerate(g_rows))}
             <div class="hint">本节先示 {TEASER_ROWS} 份 · 点上方分类卡可调阅全卷</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty"><div class="big">空</div>'
                    '<p>未检索到符合条件的档案 —— 放宽条件，或先「立即收卷」。</p>'
                    '</div>', unsafe_allow_html=True)


# ---------- 分页（仅单卷模式） / 导出 ----------

if group_sel and rows:
    p1, p2, p3 = st.columns([1.2, 2.6, 1.2])

    def _flip(d: int) -> None:
        st.session_state["page"] = max(0, min(
            st.session_state.get("page", 0) + d, total_pages - 1))

    with p1:
        st.button("◁ 上一卷", disabled=page == 0, on_click=_flip, args=(-1,),
                  use_container_width=True)
    with p2:
        st.markdown(f'<div class="pagenum" style="text-align:center;'
                    f'padding-top:8px;">— 第 {page + 1} 卷 / 共 {total_pages} 卷'
                    f'（每卷 {PAGE_SIZE} 份）—</div>', unsafe_allow_html=True)
    with p3:
        st.button("下一卷 ▷", disabled=page >= total_pages - 1, on_click=_flip,
                  args=(1,), use_container_width=True)

if rows:
    df = pd.DataFrame(rows)
    export = pd.DataFrame({
        "职位": df["title"], "公司": df["company"], "薪资": df["salary_text"],
        "月薪K(中位)": ((df["salary_min_k"].fillna(0) + df["salary_max_k"].fillna(0)) / 2)
                      .replace(0, None),
        "方向": df["keyword_group"], "性质": df["job_type"],
        "平台": df["platform"].map(PLATFORM_NAMES).fillna(df["platform"]),
        "地点": (df["city"] + "-" + df["district"]).str.rstrip("-"),
        "经验": df["experience"], "学历": df["education"],
        "联系人": df["hr_name"], "首次发现": df["first_seen_at"].str.slice(0, 10),
        "原文链接": df["url"],
    })
    st.download_button(
        "导出本次检索结果 CSV", data=export.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"提篮桥档案_{datetime.now():%Y%m%d_%H%M}.csv", mime="text/csv")


# ---------- 常见问答 ----------

st.markdown("""
<div class="faq-wrap">
  <div class="faq-cap">关于本中心 · 常见问答</div>
  <details class="faq"><summary>档案每天什么时候更新？需要我守着吗？</summary>
    <div class="ans">不需要。Windows 任务计划每天 09:30 自动向四个平台收卷一次；
    若那会儿电脑没开机，开机后会自动补跑。网页「立即收卷」按钮可随时手动加收一轮。</div>
  </details>
  <details class="faq"><summary>岗位下线了会怎么处理？</summary>
    <div class="ans">连续约一周（7 轮收卷）都没再出现的岗位自动归档，默认不再展示；
    归档满 180 天的记录彻底清理。岗位若重新挂出会自动恢复在档。</div>
  </details>
  <details class="faq"><summary>怎么申请岗位？简历投给谁？</summary>
    <div class="ans">点职位标题（或展开后的「调阅原文」）直达招聘平台原文页面，
    按原平台流程申请。本中心只做收录比对，不代收简历、不经手任何个人信息。</div>
  </details>
  <details class="faq"><summary>数据从哪里来？可靠吗？</summary>
    <div class="ans">来自猎聘、前程无忧、智联招聘、BOSS直聘的公开搜索结果，
    慢速抓取、仅供本人调阅。薪资与时效一律以平台原文为准，顶部胶囊实时显示
    各平台最近一次收卷状态。</div>
  </details>
</div>
""", unsafe_allow_html=True)


# ---------- 值班用印台（互动彩蛋） ----------

components_html(DESK_HTML, height=258, scrolling=False)


# ---------- 页脚 ----------

st.markdown(f"""
<div class="foot">
  <div class="k">本中心档案仅供本人求职参考 · 岗位详情与时效以各平台原文为准</div>
  <div class="m">TILANQIAO HUMAN RESERVE ARCHIVE · EST. {YEAR} · 沪</div>
</div>
""", unsafe_allow_html=True)
