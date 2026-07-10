import {
  useState,
  useRef,
  useEffect,
  type ReactNode,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
} from "react"
import { Link } from "react-router-dom"
import {
  MessageSquare,
  FileText,
  Scale,
  Map,
  Heart,
  ArrowRight,
  Shield,
  Brain,
  Eye,
  Gavel,
  Layers,
  Database,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  Terminal,
  type LucideIcon,
} from "lucide-react"
import { getSystemStatus, type SystemStatus } from "@/api/system"
import {
  motion,
  useMotionValue,
  useSpring,
  useTransform,
  AnimatePresence,
} from "framer-motion"
import Particles, { ParticlesProvider } from "@tsparticles/react"
import { loadSlim } from "@tsparticles/slim"

// 核心功能模块
interface FeatureCard {
  to: string
  title: string
  desc: string
  icon: LucideIcon
  gradient: string
}

const features: FeatureCard[] = [
  {
    to: "/chat",
    title: "智能咨询",
    desc: "与法律 AI 助手多轮对话，支持文件上传、视觉分析与知识库增强",
    icon: MessageSquare,
    gradient: "from-blue-500 to-cyan-500",
  },
  {
    to: "/contract",
    title: "合同诊疗",
    desc: "上传合同自动识别风险条款，给出专业修改建议与条款评分",
    icon: FileText,
    gradient: "from-emerald-500 to-teal-500",
  },
  {
    to: "/expert",
    title: "专家会诊",
    desc: "多角色 AI 专家协同分析复杂法律问题，模拟真实会诊流程",
    icon: Scale,
    gradient: "from-violet-500 to-purple-500",
  },
  {
    to: "/map",
    title: "地图浏览",
    desc: "在 3D 地图上可视化法律数据与地理信息，支持多维筛选",
    icon: Map,
    gradient: "from-amber-500 to-orange-500",
  },
  {
    to: "/relax",
    title: "放松模式",
    desc: "全屏背景轮播与背景音乐，在工作间隙舒缓身心",
    icon: Heart,
    gradient: "from-rose-500 to-pink-500",
  },
]

// 系统优势
interface Advantage {
  title: string
  desc: string
  icon: LucideIcon
}

const advantages: Advantage[] = [
  {
    title: "专业法律知识",
    desc: "内置权威法律条文与案例知识库，回答严谨可追溯",
    icon: Gavel,
  },
  {
    title: "多模型协同",
    desc: "整合多家主流大模型，按场景智能调度最优模型",
    icon: Brain,
  },
  {
    title: "视觉 AI 分析",
    desc: "支持图片上传，识别合同、证件、票据等视觉信息",
    icon: Eye,
  },
  {
    title: "法庭模拟",
    desc: "模拟庭审对抗与辩论，检验法律论证的稳健性",
    icon: Scale,
  },
  {
    title: "3D 地图",
    desc: "基于地理信息可视化法律数据，直观呈现空间分布",
    icon: Layers,
  },
  {
    title: "记忆系统",
    desc: "多轮对话记忆与上下文管理，保持咨询连贯性",
    icon: Database,
  },
]

// 快速开始步骤
interface Step {
  no: number
  title: string
  desc: string
}

const steps: Step[] = [
  {
    no: 1,
    title: "选择功能模块",
    desc: "从上方卡片中选择您需要的服务，如智能咨询或合同诊疗",
  },
  {
    no: 2,
    title: "描述您的问题",
    desc: "在对话中用自然语言描述您的法律问题，或上传相关文件",
  },
  {
    no: 3,
    title: "获取 AI 分析",
    desc: "系统将基于知识库与多模型协同，给出专业、结构化的回答",
  },
  {
    no: 4,
    title: "深入追问",
    desc: "针对回答中的疑点继续多轮追问，逐步完善您的法律方案",
  },
]

// 数字统计
interface Stat {
  value: number
  suffix: string
  label: string
}

const stats: Stat[] = [
  { value: 8, suffix: "大", label: "法律分类" },
  { value: 5, suffix: "大", label: "功能模块" },
  { value: 6, suffix: "项", label: "系统能力" },
  { value: 4, suffix: "步", label: "快速上手" },
]

// tsparticles 配置：70 个蓝色/青色粒子 + 连线效果
const LS_PARTICLES_OPTIONS = {
  fpsLimit: 60,
  fullScreen: { enable: false },
  background: { color: { value: "transparent" } },
  particles: {
    number: { value: 70 },
    color: { value: ["#7dd3fc", "#38bdf8", "#22d3ee", "#67e8f9"] },
    links: {
      enable: true,
      color: "#7dd3fc",
      distance: 140,
      opacity: 0.35,
      width: 1,
    },
    move: {
      enable: true,
      speed: 0.8,
      direction: "none" as const,
      random: true,
      straight: false,
      outModes: { default: "out" as const },
    },
    opacity: {
      value: { min: 0.3, max: 0.9 },
    },
    size: {
      value: { min: 1, max: 3 },
    },
  },
  detectRetina: true,
}

// 动画 keyframes（注入到 <style>）
const LS_ANIMATIONS = `
@keyframes ls-aurora {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
@keyframes ls-fade-up {
  0% { transform: translateY(20px); opacity: 0; }
  100% { transform: translateY(0); opacity: 1; }
}
@keyframes ls-shine {
  0% { transform: translateX(-160%) skewX(-20deg); }
  100% { transform: translateX(260%) skewX(-20deg); }
}
.ls-shine-btn { position: relative; overflow: hidden; }
.ls-shine-btn::before {
  content: "";
  position: absolute;
  top: 0; left: 0;
  width: 60%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(125,211,252,0.55), transparent);
  transform: translateX(-160%) skewX(-20deg);
  pointer-events: none;
}
.ls-shine-btn:hover::before {
  animation: ls-shine 0.9s ease;
}
@media (prefers-reduced-motion: reduce) {
  .ls-shine-btn::before { animation: none !important; }
  .ls-aurora-anim { animation: none !important; }
}
`

// 滚动进入视口 hook
function useInView<T extends HTMLElement = HTMLDivElement>(threshold = 0.15) {
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === "undefined") {
      setInView(true)
      return
    }
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          obs.disconnect()
        }
      },
      { threshold }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [threshold])
  return { ref, inView }
}

// 数字滚动 hook
function useCountUp(target: number, active: boolean, duration = 1500) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (!active) return
    let raf = 0
    let start: number | null = null
    const step = (ts: number) => {
      if (start === null) start = ts
      const progress = Math.min((ts - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(eased * target))
      if (progress < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [active, target, duration])
  return value
}

// 入场动画包装组件：淡入 + 上移
function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode
  delay?: number
  className?: string
}) {
  const { ref, inView } = useInView<HTMLDivElement>()
  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: inView ? 1 : 0,
        transform: inView ? "translateY(0)" : "translateY(24px)",
        transition: `opacity 0.6s ease ${delay}ms, transform 0.6s ease ${delay}ms`,
        willChange: "opacity, transform",
      }}
    >
      {children}
    </div>
  )
}

// 3D 倾斜卡片：framer-motion 鼠标位置驱动 rotateX/rotateY + 悬停上浮
function TiltCard({
  children,
  className = "",
}: {
  children: ReactNode
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const mouseX = useMotionValue(0.5)
  const mouseY = useMotionValue(0.5)
  const rotateX = useSpring(useTransform(mouseY, [0, 1], [8, -8]), {
    stiffness: 300,
    damping: 20,
  })
  const rotateY = useSpring(useTransform(mouseX, [0, 1], [-8, 8]), {
    stiffness: 300,
    damping: 20,
  })

  const handleMove = (e: ReactMouseEvent<HTMLDivElement>) => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    mouseX.set((e.clientX - rect.left) / rect.width)
    mouseY.set((e.clientY - rect.top) / rect.height)
  }
  const handleLeave = () => {
    mouseX.set(0.5)
    mouseY.set(0.5)
  }
  return (
    <motion.div
      ref={ref}
      className={className}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      style={{ rotateX, rotateY, transformPerspective: 1000 }}
      whileHover={{ y: -6 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
    >
      {children}
    </motion.div>
  )
}

// 统计项：滚动入视时数字从 0 滚动到目标值
function StatItem({ value, suffix, label }: Stat) {
  const { ref, inView } = useInView<HTMLDivElement>()
  const n = useCountUp(value, inView)
  return (
    <div ref={ref} className="text-center">
      <div className="bg-gradient-to-br from-blue-600 to-indigo-600 bg-clip-text text-4xl font-extrabold text-transparent md:text-5xl">
        {n}
        <span className="text-2xl md:text-3xl">{suffix}</span>
      </div>
      <div className="mt-1 text-xs text-slate-500 md:text-sm">{label}</div>
    </div>
  )
}

// 首次进入全屏开场动画：Logo 放大 + 淡出（sessionStorage 记录避免重复播放）
function IntroOverlay() {
  const [show, setShow] = useState(() => {
    try {
      return sessionStorage.getItem("ls_intro_played") !== "1"
    } catch {
      return false
    }
  })

  useEffect(() => {
    if (!show) return
    const timer = setTimeout(() => {
      setShow(false)
      try {
        sessionStorage.setItem("ls_intro_played", "1")
      } catch {
        // 忽略 sessionStorage 异常
      }
    }, 2400)
    return () => clearTimeout(timer)
  }, [show])

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950"
          initial={{ opacity: 1 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.7, ease: "easeInOut" }}
        >
          <motion.div
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: [0.5, 1.1, 1], opacity: [0, 1, 1] }}
            transition={{ duration: 1.5, times: [0, 0.6, 1], ease: "easeOut" }}
            className="text-center"
          >
            <div className="bg-gradient-to-r from-blue-300 via-cyan-200 to-emerald-200 bg-clip-text text-5xl font-bold tracking-tight text-transparent md:text-8xl">
              LvsheProject
            </div>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8, duration: 0.6 }}
              className="mt-3 text-sm font-medium tracking-widest text-slate-400"
            >
              法律 AI Agent 系统
            </motion.div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// 首页
export default function Home() {
  const [devOpen, setDevOpen] = useState(false)
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const toggleDev = async () => {
    const next = !devOpen
    setDevOpen(next)
    if (next && !status && !statusError) {
      setStatusLoading(true)
      try {
        const res = await getSystemStatus()
        setStatus(res)
      } catch (e) {
        setStatusError(e instanceof Error ? e.message : "获取状态失败")
      } finally {
        setStatusLoading(false)
      }
    }
  }

  const heroFade = (delay: number): CSSProperties => ({
    animation: `ls-fade-up 0.7s ease ${delay}ms both`,
    willChange: "opacity, transform",
  })

  return (
    <div className="min-h-full bg-slate-50">
      <style dangerouslySetInnerHTML={{ __html: LS_ANIMATIONS }} />
      <IntroOverlay />

      {/* Hero 区域 */}
      <section className="relative overflow-hidden">
        {/* 渐变背景（流动） */}
        <div
          className="ls-aurora-anim absolute inset-0 bg-gradient-to-br from-slate-900 via-blue-900 to-indigo-900"
          style={{ backgroundSize: "200% 200%", animation: "ls-aurora 14s ease infinite" }}
        />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(56,189,248,0.25),transparent_55%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,rgba(168,85,247,0.2),transparent_55%)]" />
        {/* 动态光斑 */}
        <div className="absolute -left-20 top-10 h-72 w-72 animate-pulse rounded-full bg-blue-500/20 blur-3xl" />
        <div className="absolute -right-20 bottom-0 h-80 w-80 animate-pulse rounded-full bg-purple-500/20 blur-3xl [animation-delay:1s]" />
        {/* 网格纹理 */}
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "linear-gradient(to right, white 1px, transparent 1px), linear-gradient(to bottom, white 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
        {/* 粒子层（tsparticles：蓝色/青色粒子 + 连线） */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{ transform: "translateZ(0)" }}
        >
          <ParticlesProvider init={loadSlim}>
            <Particles id="ls-particles" options={LS_PARTICLES_OPTIONS} />
          </ParticlesProvider>
        </div>

        <div className="relative mx-auto max-w-6xl px-8 py-20">
          <div
            className="flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 text-xs font-medium text-blue-200 backdrop-blur w-fit"
            style={heroFade(0)}
          >
            <Shield className="h-3.5 w-3.5" />
            新一代法律人工智能平台
          </div>
          <h1
            className="mt-6 max-w-3xl text-5xl font-bold leading-tight tracking-tight text-white"
            style={heroFade(120)}
          >
            LvsheProject{" "}
            <span className="bg-gradient-to-r from-blue-300 via-cyan-200 to-emerald-200 bg-clip-text text-transparent">
              法律 AI Agent 系统
            </span>
          </h1>
          <p
            className="mt-5 max-w-2xl text-lg leading-relaxed text-slate-300"
            style={heroFade(220)}
          >
            集成智能咨询、合同诊疗、专家会诊与地图可视化的新一代法律 AI 平台。
            基于多模型协同、视觉分析与知识库增强，为您提供专业、严谨、可追溯的法律智能服务。
          </p>
          <div className="mt-8 flex flex-wrap gap-3" style={heroFade(320)}>
            <Link
              to="/chat"
              className="ls-shine-btn group inline-flex items-center gap-2 rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-slate-900 shadow-lg transition hover:bg-slate-100"
            >
              立即开始咨询
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
            </Link>
            <a
              href="#features"
              className="ls-shine-btn inline-flex items-center gap-2 rounded-lg border border-white/20 bg-white/5 px-5 py-2.5 text-sm font-semibold text-white backdrop-blur transition hover:bg-white/10"
            >
              浏览功能
            </a>
          </div>
        </div>
      </section>

      {/* 数字统计 */}
      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-6 px-8 py-10 md:grid-cols-4">
          {stats.map((s) => (
            <StatItem key={s.label} {...s} />
          ))}
        </div>
      </section>

      {/* 核心功能模块 */}
      <section id="features" className="mx-auto max-w-6xl px-8 py-16">
        <Reveal>
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-slate-900">核心功能模块</h2>
            <p className="mt-2 text-sm text-slate-500">
              五大功能覆盖法律咨询的完整场景
            </p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f, idx) => (
            <Reveal key={f.to} delay={idx * 80}>
              <TiltCard>
                <Link
                  to={f.to}
                  className="group relative block overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition-all hover:border-transparent hover:shadow-xl"
                >
                  <div
                    className={`mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${f.gradient} text-white shadow-md`}
                  >
                    <f.icon className="h-6 w-6" />
                  </div>
                  <h3 className="mb-2 text-lg font-semibold text-slate-900">
                    {f.title}
                  </h3>
                  <p className="text-sm leading-relaxed text-slate-500">
                    {f.desc}
                  </p>
                  <div className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-blue-600 opacity-0 transition group-hover:opacity-100">
                    进入
                    <ChevronRight className="h-4 w-4" />
                  </div>
                </Link>
              </TiltCard>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 系统优势 */}
      <section className="bg-white py-16">
        <div className="mx-auto max-w-6xl px-8">
          <Reveal>
            <div className="mb-8 text-center">
              <h2 className="text-2xl font-bold text-slate-900">系统优势</h2>
              <p className="mt-2 text-sm text-slate-500">
                专业、协同、智能的法律 AI 能力
              </p>
            </div>
          </Reveal>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {advantages.map((a, idx) => (
              <Reveal key={a.title} delay={idx * 70}>
                <div className="h-full rounded-2xl border border-slate-200 bg-slate-50/50 p-6 transition hover:border-blue-200 hover:bg-white hover:shadow-md">
                  <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100 text-blue-600">
                    <a.icon className="h-5 w-5" />
                  </div>
                  <h3 className="mb-1.5 text-base font-semibold text-slate-900">
                    {a.title}
                  </h3>
                  <p className="text-sm leading-relaxed text-slate-500">
                    {a.desc}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 快速开始教程 */}
      <section className="mx-auto max-w-6xl px-8 py-16">
        <Reveal>
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-slate-900">快速开始</h2>
            <p className="mt-2 text-sm text-slate-500">
              四步即可获得专业的法律 AI 服务
            </p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s, idx) => (
            <Reveal key={s.no} delay={idx * 90}>
              <div className="relative h-full">
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-sm font-bold text-white">
                    {s.no}
                  </div>
                  <h3 className="mb-1.5 text-base font-semibold text-slate-900">
                    {s.title}
                  </h3>
                  <p className="text-sm leading-relaxed text-slate-500">
                    {s.desc}
                  </p>
                </div>
                {idx < steps.length - 1 && (
                  <ChevronRight className="absolute -right-3 top-1/2 hidden h-5 w-5 -translate-y-1/2 text-slate-300 lg:block" />
                )}
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 底部：开发者模式折叠区 */}
      <footer className="border-t border-slate-200 bg-slate-900 py-8">
        <div className="mx-auto max-w-6xl px-8">
          <button
            onClick={toggleDev}
            className="flex w-full items-center justify-between text-left"
          >
            <span className="inline-flex items-center gap-2 text-sm font-medium text-slate-300">
              <Terminal className="h-4 w-4" />
              开发者模式
            </span>
            <ChevronDown
              className={`h-4 w-4 text-slate-400 transition ${
                devOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {devOpen && (
            <div className="mt-4 rounded-lg border border-slate-700 bg-slate-950/60 p-4 font-mono text-xs text-slate-300">
              <div className="mb-2 flex items-center gap-2 text-slate-400">
                <CircleCheck
                  className={`h-3.5 w-3.5 ${
                    status ? "text-emerald-400" : "text-slate-500"
                  }`}
                />
                后端状态：{statusLoading ? "查询中..." : status ? "在线" : statusError ? "离线" : "未知"}
              </div>
              {statusError && (
                <div className="text-rose-400">错误：{statusError}</div>
              )}
              {status && (
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-slate-400">
                  {JSON.stringify(status, null, 2)}
                </pre>
              )}
              <div className="mt-2 text-slate-500">
                端点：GET /api/status
              </div>
            </div>
          )}

          <div className="mt-6 border-t border-slate-800 pt-6 text-center text-xs text-slate-500">
            LvsheProject 法律 AI Agent 系统 · 前端 React + TypeScript + Tailwind
          </div>
        </div>
      </footer>
    </div>
  )
}
