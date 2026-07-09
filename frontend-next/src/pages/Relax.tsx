import { useCallback, useEffect, useRef, useState } from "react"
import {
  SkipBack,
  SkipForward,
  Repeat,
  Repeat1,
  Music,
  ListMusic,
  Volume2,
  VolumeX,
  Eye,
  PanelLeft,
  type LucideIcon,
} from "lucide-react"
import { backgroundImages, musicTracks } from "@/data/relax-assets"
import { cn } from "@/lib/utils"

// 播放模式
type PlayMode = "sequence" | "repeat-one"

export default function Relax() {
  // ====== 资源配置 ======
  // 背景图：请将图片放入 frontend-next/public/relax/backgrounds/ 目录
  // 背景音乐：请将音频文件放入 frontend-next/public/relax/music/ 目录
  // 配置文件：在 frontend-next/src/data/relax-assets.ts 中编辑资源列表

  // 背景
  const [bgIndex, setBgIndex] = useState(0)
  const [bgEnabled, setBgEnabled] = useState(true) // 默认开启背景图
  const [blurEnabled, setBlurEnabled] = useState(false) // 默认关闭背景模糊
  const [carouselInterval, setCarouselInterval] = useState(15) // 秒

  // 音乐
  const [trackIndex, setTrackIndex] = useState(0)
  const [musicOn, setMusicOn] = useState(false) // 开关控制，无单独播放/暂停按钮
  const [volume, setVolume] = useState(0.6)
  const [muted, setMuted] = useState(false)
  const [playMode, setPlayMode] = useState<PlayMode>("sequence")

  // 面板显隐
  const [showPlaylist, setShowPlaylist] = useState(true)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const carouselTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const currentTrack = musicTracks[trackIndex]
  const currentBg = backgroundImages[bgIndex]

  // 背景轮播
  useEffect(() => {
    if (!bgEnabled || backgroundImages.length <= 1) {
      return
    }
    carouselTimerRef.current = setInterval(() => {
      setBgIndex((i) => (i + 1) % backgroundImages.length)
    }, carouselInterval * 1000)
    return () => {
      if (carouselTimerRef.current) clearInterval(carouselTimerRef.current)
    }
  }, [bgEnabled, carouselInterval, bgIndex])

  // 音量同步
  useEffect(() => {
    const audio = audioRef.current
    if (audio) {
      audio.volume = muted ? 0 : volume
    }
  }, [volume, muted])

  // 播放/暂停控制
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    audio.src = currentTrack.url
    audio.load()
    if (musicOn) {
      audio.play().catch(() => {
        // 资源不存在或浏览器策略阻止时静默处理
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trackIndex])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    if (musicOn) {
      audio.play().catch(() => {})
    } else {
      audio.pause()
    }
  }, [musicOn])

  // 上一曲 / 下一曲
  const handlePrev = useCallback(() => {
    setTrackIndex((i) =>
      i === 0 ? musicTracks.length - 1 : i - 1,
    )
  }, [])

  const handleNext = useCallback(() => {
    setTrackIndex((i) => (i + 1) % musicTracks.length)
  }, [])

  // 音频播放结束：按播放模式决定下一步
  const handleEnded = useCallback(() => {
    if (playMode === "repeat-one") {
      const audio = audioRef.current
      if (audio) {
        audio.currentTime = 0
        audio.play().catch(() => {})
      }
    } else {
      handleNext()
    }
  }, [playMode, handleNext])

  // 切换播放模式
  const togglePlayMode = useCallback(() => {
    setPlayMode((m) => (m === "sequence" ? "repeat-one" : "sequence"))
  }, [])

  // 切换音乐开关
  const toggleMusic = useCallback(() => setMusicOn((v) => !v), [])

  // 切换背景模糊（关闭时隐藏右面板所有文字，只显示背景图）
  const toggleBlur = useCallback(() => setBlurEnabled((v) => !v), [])

  // 切换静音
  const toggleMute = useCallback(() => setMuted((v) => !v), [])

  // 切换播放列表显隐
  const togglePlaylist = useCallback(() => setShowPlaylist((v) => !v), [])

  // 选中播放列表曲目
  const selectTrack = useCallback((idx: number) => {
    setTrackIndex(idx)
  }, [])

  // 选中背景
  const selectBg = useCallback((idx: number) => {
    setBgIndex(idx)
  }, [])

  // 当背景模糊关闭时，右面板所有文字隐藏，只显示背景图
  const showText = blurEnabled

  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-900">
      {/* ====== 全屏背景图 ====== */}
      {bgEnabled ? (
        <div
          className="absolute inset-0 bg-cover bg-center transition-all duration-700 ease-out"
          style={{
            backgroundImage: `url(${currentBg})`,
            filter: blurEnabled ? "blur(20px) saturate(120%)" : "none",
            transform: blurEnabled ? "scale(1.05)" : "scale(1)",
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-slate-800 via-indigo-900 to-slate-900" />
      )}

      {/* 模糊模式下的暗色遮罩，提升文字对比度 */}
      {blurEnabled && (
        <div className="absolute inset-0 bg-black/30" />
      )}

      {/* 隐藏的音频元素 */}
      <audio
        ref={audioRef}
        onEnded={handleEnded}
        preload="auto"
      />

      {/* ====== 顶部毛玻璃切换按钮（始终可见，用于在纯净模式下唤回面板）====== */}
      <button
        onClick={toggleBlur}
        className="glass-btn absolute right-5 top-5 z-30 flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-xs font-medium text-white backdrop-blur-md"
        title={blurEnabled ? "进入纯净壁纸模式" : "显示控制面板"}
      >
        {blurEnabled ? <Eye className="h-3.5 w-3.5" /> : <PanelLeft className="h-3.5 w-3.5" />}
        {showText && (blurEnabled ? "纯净模式" : "显示面板")}
      </button>

      {/* ====== 左侧毛玻璃控制面板 ====== */}
      <div
        className={cn(
          "absolute left-6 top-1/2 z-20 w-80 -translate-y-1/2 rounded-2xl border border-white/20 p-5 transition-all duration-300",
          "bg-white/10 backdrop-blur-2xl backdrop-saturate-150",
          blurEnabled
            ? "opacity-100"
            : "pointer-events-none -translate-x-[120%] opacity-0",
        )}
        style={{
          background:
            "linear-gradient(135deg, rgba(255,255,255,0.12), rgba(255,255,255,0.04))",
        }}
      >
        {/* 标题 */}
        {showText && (
          <div className="mb-5 flex items-center gap-2 text-white">
            <Music className="h-4 w-4" />
            <h2 className="text-sm font-semibold tracking-wide">放松模式</h2>
          </div>
        )}

        {/* 当前曲目信息 */}
        {showText && (
          <div className="mb-5 rounded-xl bg-white/5 p-3">
            <p className="truncate text-base font-semibold text-white">
              {currentTrack.title}
            </p>
            <p className="mt-0.5 truncate text-xs text-white/60">
              {currentTrack.artist}
            </p>
          </div>
        )}

        {/* 播放控制：上一曲 / 音乐开关 / 下一曲 / 播放模式 */}
        {showText && (
          <div className="mb-5 flex items-center justify-center gap-4">
            <button
              onClick={handlePrev}
              className="glass-btn flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
              title="上一曲"
            >
              <SkipBack className="h-4 w-4" />
            </button>

            {/* 音乐开关（开关控制，无单独播放/暂停按钮）*/}
            <button
              onClick={toggleMusic}
              className={cn(
                "glass-btn flex h-12 w-12 items-center justify-center rounded-full text-white transition-colors",
                musicOn
                  ? "bg-gradient-to-br from-emerald-400 to-teal-500"
                  : "bg-white/10 hover:bg-white/20",
              )}
              title={musicOn ? "关闭音乐" : "开启音乐"}
            >
              {musicOn ? (
                <Music className="h-5 w-5" />
              ) : (
                <Music className="h-5 w-5 opacity-50" />
              )}
            </button>

            <button
              onClick={handleNext}
              className="glass-btn flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
              title="下一曲"
            >
              <SkipForward className="h-4 w-4" />
            </button>

            <button
              onClick={togglePlayMode}
              className={cn(
                "glass-btn flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors",
                playMode === "repeat-one"
                  ? "bg-gradient-to-br from-violet-400 to-purple-500"
                  : "bg-white/10 hover:bg-white/20",
              )}
              title={
                playMode === "sequence" ? "顺序播放" : "单曲循环"
              }
            >
              {playMode === "sequence" ? (
                <Repeat className="h-4 w-4" />
              ) : (
                <Repeat1 className="h-4 w-4" />
              )}
            </button>
          </div>
        )}

        {/* 音量控制 */}
        {showText && (
          <div className="mb-4">
            <div className="mb-2 flex items-center justify-between text-xs text-white/70">
              <span className="flex items-center gap-1.5">
                {muted || volume === 0 ? (
                  <VolumeX className="h-3.5 w-3.5" />
                ) : (
                  <Volume2 className="h-3.5 w-3.5" />
                )}
                音量
              </span>
              <button
                onClick={toggleMute}
                className="text-white/60 transition hover:text-white"
              >
                {muted ? "取消静音" : "静音"}
              </button>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={muted ? 0 : volume}
              onChange={(e) => {
                setVolume(Number(e.target.value))
                if (muted && Number(e.target.value) > 0) setMuted(false)
              }}
              className="glass-slider"
            />
          </div>
        )}

        {/* 背景轮播间隔 */}
        {showText && (
          <div className="mb-4">
            <div className="mb-2 flex items-center justify-between text-xs text-white/70">
              <span>轮播间隔</span>
              <span>{carouselInterval} 秒</span>
            </div>
            <input
              type="range"
              min={5}
              max={60}
              step={1}
              value={carouselInterval}
              onChange={(e) => setCarouselInterval(Number(e.target.value))}
              className="glass-slider"
            />
          </div>
        )}

        {/* 开关组：背景图 / 背景模糊 / 播放列表面板 */}
        {showText && (
          <div className="space-y-2 border-t border-white/10 pt-4">
            <ToggleRow
              label="背景图"
              enabled={bgEnabled}
              onToggle={() => setBgEnabled((v) => !v)}
            />
            <ToggleRow
              label="背景模糊"
              enabled={blurEnabled}
              onToggle={toggleBlur}
            />
            <ToggleRow
              label="播放列表"
              enabled={showPlaylist}
              onToggle={togglePlaylist}
            />
          </div>
        )}
      </div>

      {/* ====== 右侧播放列表面板 ====== */}
      {blurEnabled && showPlaylist && (
        <div
          className="absolute right-6 top-1/2 z-20 max-h-[70%] w-72 -translate-y-1/2 overflow-hidden rounded-2xl border border-white/20 backdrop-blur-2xl backdrop-saturate-150"
          style={{
            background:
              "linear-gradient(135deg, rgba(255,255,255,0.12), rgba(255,255,255,0.04))",
          }}
        >
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <span className="flex items-center gap-2 text-sm font-semibold text-white">
              <ListMusic className="h-4 w-4" />
              播放列表
            </span>
            <span className="text-xs text-white/50">
              {musicTracks.length} 首
            </span>
          </div>
          <div className="max-h-96 overflow-y-auto px-2 py-2">
            {musicTracks.map((track, idx) => (
              <button
                key={`${track.title}-${idx}`}
                onClick={() => selectTrack(idx)}
                className={cn(
                  "music-card flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left",
                  idx === trackIndex
                    ? "bg-white/15 text-white"
                    : "text-white/70 hover:bg-white/5",
                )}
              >
                <span
                  className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-medium",
                    idx === trackIndex
                      ? "bg-gradient-to-br from-emerald-400 to-teal-500 text-white"
                      : "bg-white/10 text-white/60",
                  )}
                >
                  {idx === trackIndex && musicOn ? (
                    <Music className="h-3.5 w-3.5 animate-pulse" />
                  ) : (
                    idx + 1
                  )}
                </span>
                <span className="flex-1 truncate">
                  <span className="block truncate text-sm font-medium">
                    {track.title}
                  </span>
                  <span className="block truncate text-xs text-white/50">
                    {track.artist}
                  </span>
                </span>
              </button>
            ))}
          </div>

          {/* 背景图缩略图选择 */}
          {bgEnabled && backgroundImages.length > 0 && (
            <div className="border-t border-white/10 px-3 py-3">
              <p className="mb-2 px-1 text-xs text-white/60">背景选择</p>
              <div className="grid grid-cols-3 gap-2">
                {backgroundImages.map((bg, idx) => (
                  <button
                    key={`${bg}-${idx}`}
                    onClick={() => selectBg(idx)}
                    className={cn(
                      "aspect-video overflow-hidden rounded-md border-2 transition",
                      idx === bgIndex
                        ? "border-emerald-400"
                        : "border-transparent opacity-70 hover:opacity-100",
                    )}
                  >
                    <img
                      src={bg}
                      alt={`背景 ${idx + 1}`}
                      className="h-full w-full object-cover"
                      onError={(e) => {
                        // 资源缺失时隐藏缩略图
                        ;(e.target as HTMLImageElement).style.display = "none"
                      }}
                    />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 纯净模式提示（背景模糊关闭时）*/}
      {!blurEnabled && (
        <div className="pointer-events-none absolute bottom-6 left-1/2 z-20 -translate-x-1/2 text-center">
          <p className="text-xs text-white/40">纯净壁纸模式</p>
        </div>
      )}
    </div>
  )
}

// 毛玻璃开关行
function ToggleRow({
  label,
  enabled,
  onToggle,
  icon: Icon,
}: {
  label: string
  enabled: boolean
  onToggle: () => void
  icon?: LucideIcon
}) {
  return (
    <div className="flex items-center justify-between text-xs text-white/80">
      <span className="flex items-center gap-1.5">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        {label}
      </span>
      <button
        onClick={onToggle}
        className={cn(
          "relative h-5 w-10 rounded-full transition-colors",
          enabled ? "bg-emerald-500/80" : "bg-white/20",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all",
            enabled ? "left-[22px]" : "left-0.5",
          )}
        />
      </button>
    </div>
  )
}
