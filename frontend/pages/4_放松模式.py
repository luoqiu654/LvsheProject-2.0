from __future__ import annotations

import base64
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(
    page_title="放松模式 - 律社法律AI",
    page_icon="🎵",
    layout="wide",
)

# ========== 资源路径 ==========
BG_DIR = ROOT / "frontend" / "assets" / "backgrounds"
MUSIC_DIR = ROOT / "frontend" / "assets" / "music"


def get_background_images() -> list[Path]:
    """获取背景图片列表。"""
    if not BG_DIR.exists():
        return []
    supported = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    images = sorted(
        [f for f in BG_DIR.iterdir() if f.suffix.lower() in supported],
        key=lambda x: x.stem,
    )
    return images[:9]


def get_music_files() -> list[Path]:
    """获取音乐文件列表。"""
    if not MUSIC_DIR.exists():
        return []
    supported = {".mp3", ".wav", ".ogg"}
    musics = sorted(
        [f for f in MUSIC_DIR.iterdir() if f.suffix.lower() in supported],
        key=lambda x: x.stem,
    )
    return musics[:9]


def file_to_base64(file_path: Path) -> str:
    """将文件转换为 base64。"""
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    ext = file_path.suffix.lower().lstrip(".")
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
    }
    mime = mime_map.get(ext, "application/octet-stream")
    return f"data:{mime};base64,{data}"


def apply_background_style(
    enabled: bool,
    blur_enabled: bool,
    slideshow_enabled: bool,
    interval: int = 8,
):
    """应用背景样式。"""
    images = get_background_images()

    if not enabled or not images:
        st.markdown(
            """
            <style>
            .stApp {
                background: none;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        return

    bg_images = [file_to_base64(img) for img in images]
    blur_amount = "15px" if blur_enabled else "0px"

    if len(bg_images) == 1 or not slideshow_enabled:
        css = f"""
        <style>
        .stApp {{
            background-image: url("{bg_images[0]}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
            transition: background-image 1s ease-in-out;
        }}
        .stApp::before {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            backdrop-filter: blur({blur_amount});
            -webkit-backdrop-filter: blur({blur_amount});
            z-index: 0;
            pointer-events: none;
        }}
        .stApp > div {{
            position: relative;
            z-index: 1;
        }}
        </style>
        """
    else:
        duration = len(bg_images) * interval
        keyframes = ""
        for i, img in enumerate(bg_images):
            pct = (i / len(bg_images)) * 100
            keyframes += f"    {pct:.0f}% {{ background-image: url('{img}'); }}\n"

        css = f"""
        <style>
        .stApp {{
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
            animation: bgSlideshow {duration}s infinite ease-in-out;
        }}
        @keyframes bgSlideshow {{
        {keyframes}
            100% {{ background-image: url('{bg_images[0]}'); }}
        }}
        .stApp::before {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            backdrop-filter: blur({blur_amount});
            -webkit-backdrop-filter: blur({blur_amount});
            z-index: 0;
            pointer-events: none;
        }}
        .stApp > div {{
            position: relative;
            z-index: 1;
        }}
        </style>
        """

    st.markdown(css, unsafe_allow_html=True)


# ========== 页面标题 ==========
st.markdown(
    """
    <div style="text-align: center; padding: 2rem 0;">
        <h1 style="font-size: 3rem; margin-bottom: 0.5rem;">🌿 放松模式</h1>
        <p style="font-size: 1.2rem; opacity: 0.8;">让音乐与美景伴随你的学习与工作</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

# ========== 主内容区：两栏布局 ==========
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🖼️ 视觉设置")

    bg_images = get_background_images()
    bg_enabled = st.toggle("启用背景图片", value=True, key="bg_enabled")
    bg_blur = st.toggle("背景虚化效果", value=True, key="bg_blur", disabled=not bg_enabled)
    bg_slideshow = st.toggle("自动轮播", value=True, key="bg_slideshow", disabled=not bg_enabled or len(bg_images) <= 1)
    bg_interval = st.slider(
        "轮播间隔（秒）",
        min_value=3,
        max_value=30,
        value=10,
        step=1,
        key="bg_interval",
        disabled=not bg_enabled or not bg_slideshow,
    )

    if bg_images:
        st.success(f"✅ 已加载 {len(bg_images)} 张背景图片")
        with st.expander("查看背景图片列表"):
            for i, img in enumerate(bg_images, 1):
                st.caption(f"{i}. {img.name}")
    else:
        st.warning("⚠️ 未检测到背景图片")
        st.caption("请将图片放入 `frontend/assets/backgrounds/` 目录")

with col2:
    st.subheader("🎵 音乐设置")

    music_files = get_music_files()
    music_enabled = st.toggle("启用背景音乐", value=False, key="music_enabled")

    if music_files and music_enabled:
        # 音乐选择
        music_names = [f.stem for f in music_files]
        default_idx = st.session_state.get("current_music_idx", 0)
        if default_idx >= len(music_names):
            default_idx = 0

        selected_music = st.selectbox(
            "选择曲目",
            options=music_names,
            index=default_idx,
            key="selected_music",
        )
        current_idx = music_names.index(selected_music)
        st.session_state.current_music_idx = current_idx

        # 音量控制
        volume = st.slider("音量", min_value=0, max_value=100, value=50, key="music_volume")

        # 循环模式
        loop_mode = st.radio(
            "播放模式",
            options=["列表循环", "单曲循环", "顺序播放"],
            horizontal=True,
            key="loop_mode",
        )

        # 播放音乐
        current_music = music_files[current_idx]
        music_b64 = file_to_base64(current_music)

        # 自定义音频播放器
        loop_attr = "loop" if loop_mode == "单曲循环" else ""
        audio_html = f"""
        <audio id="relax-player" {loop_attr} autoplay>
            <source src="{music_b64}" type="audio/mpeg">
        </audio>
        <script>
            const audio = document.getElementById('relax-player');
            audio.volume = {volume / 100};
        </script>
        """
        st.markdown(audio_html, unsafe_allow_html=True)

        st.success(f"🎵 正在播放：{selected_music}")
        st.caption(f"播放模式：{loop_mode}")

        # 播放列表
        with st.expander("📋 播放列表"):
            for i, name in enumerate(music_names, 1):
                marker = "▶" if i - 1 == current_idx else "  "
                st.text(f"{marker} {i}. {name}")

    elif not music_files:
        st.warning("⚠️ 未检测到音乐文件")
        st.caption("请将 MP3 文件放入 `frontend/assets/music/` 目录")
    else:
        st.info("🎵 开启开关播放背景音乐")

# 应用背景样式
apply_background_style(
    enabled=bg_enabled,
    blur_enabled=bg_blur,
    slideshow_enabled=bg_slideshow,
    interval=bg_interval,
)

st.divider()

# ========== 底部提示 ==========
st.markdown(
    """
    <div style="text-align: center; padding: 1rem; opacity: 0.7;">
        <p>💡 小贴士：搭配背景图片和轻音乐，让法律咨询变成一种享受</p>
        <p style="font-size: 0.9rem;">图片目录：<code>frontend/assets/backgrounds/</code> | 音乐目录：<code>frontend/assets/music/</code></p>
    </div>
    """,
    unsafe_allow_html=True,
)
