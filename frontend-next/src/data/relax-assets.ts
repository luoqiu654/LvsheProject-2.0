// ====== 资源配置 ======
// 背景图：请将图片放入 frontend-next/public/relax/backgrounds/ 目录
// 背景音乐：请将音频文件放入 frontend-next/public/relax/music/ 目录
// 配置文件：在 frontend-next/src/data/relax-assets.ts 中编辑资源列表
//
// 使用说明：
// 1. 将你的背景图片（建议 .jpg/.png，分辨率 1920x1080 以上）放入
//    frontend-next/public/relax/backgrounds/ 目录，例如 bg-1.jpg、bg-2.jpg ...
// 2. 将你的背景音乐（建议 .mp3/.ogg）放入
//    frontend-next/public/relax/music/ 目录，例如 track-1.mp3 ...
// 3. 在下方数组中按需增删条目，url 字段对应 public 目录下的相对路径
//    （以 / 开头表示从 public 根目录引用，例如 /relax/backgrounds/bg-1.jpg）

// 背景图片列表（默认引用 /relax/backgrounds/ 下的图片）
// 如未放置真实图片，组件会使用渐变兜底背景，不会报错
export const backgroundImages: string[] = [
  "/relax/backgrounds/1.jpg",
  "/relax/backgrounds/2.jpg",
  "/relax/backgrounds/3.jpg",
  "/relax/backgrounds/4.jpg",
  "/relax/backgrounds/5.jpg",
  "/relax/backgrounds/6.jpg",
  "/relax/backgrounds/7.jpg",
  "/relax/backgrounds/8.jpg",
  "/relax/backgrounds/9.jpg",
]

// 音乐曲目
export interface MusicTrack {
  title: string
  artist: string
  url: string
}

// 背景音乐列表（默认引用 /relax/music/ 下的音频）
// 如未放置真实音频，播放器仍可点击但无法出声，不会阻断界面
export const musicTracks: MusicTrack[] = [
  {
    title: "山间清风",
    artist: "自然之声",
    url: "/relax/music/1.wav",
  },
  {
    title: "湖畔晨雾",
    artist: "自然之声",
    url: "/relax/music/2.mp3",
  },
  {
    title: "林间漫步",
    artist: "自然之声",
    url: "/relax/music/track-3.mp3",
  },
  {
    title: "星河夜曲",
    artist: "自然之声",
    url: "/relax/music/track-4.mp3",
  },
  {
    title: "雨后初晴",
    artist: "自然之声",
    url: "/relax/music/track-5.mp3",
  },
  {
    title: "云海日出",
    artist: "自然之声",
    url: "/relax/music/track-6.mp3",
  },
]
