import { useState } from "react"
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

  return (
    <div className="min-h-full bg-slate-50">
      {/* Hero 区域 */}
      <section className="relative overflow-hidden">
        {/* 渐变背景 */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-blue-900 to-indigo-900" />
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

        <div className="relative mx-auto max-w-6xl px-8 py-20">
          <div className="flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 text-xs font-medium text-blue-200 backdrop-blur w-fit">
            <Shield className="h-3.5 w-3.5" />
            新一代法律人工智能平台
          </div>
          <h1 className="mt-6 max-w-3xl text-5xl font-bold leading-tight tracking-tight text-white">
            LvsheProject{" "}
            <span className="bg-gradient-to-r from-blue-300 via-cyan-200 to-emerald-200 bg-clip-text text-transparent">
              法律 AI Agent 系统
            </span>
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-slate-300">
            集成智能咨询、合同诊疗、专家会诊与地图可视化的新一代法律 AI 平台。
            基于多模型协同、视觉分析与知识库增强，为您提供专业、严谨、可追溯的法律智能服务。
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/chat"
              className="group inline-flex items-center gap-2 rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-slate-900 shadow-lg transition hover:bg-slate-100"
            >
              立即开始咨询
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
            </Link>
            <a
              href="#features"
              className="inline-flex items-center gap-2 rounded-lg border border-white/20 bg-white/5 px-5 py-2.5 text-sm font-semibold text-white backdrop-blur transition hover:bg-white/10"
            >
              浏览功能
            </a>
          </div>
        </div>
      </section>

      {/* 核心功能模块 */}
      <section id="features" className="mx-auto max-w-6xl px-8 py-16">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-slate-900">核心功能模块</h2>
          <p className="mt-2 text-sm text-slate-500">
            五大功能覆盖法律咨询的完整场景
          </p>
        </div>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <Link
              key={f.to}
              to={f.to}
              className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition-all hover:-translate-y-1 hover:border-transparent hover:shadow-xl"
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
          ))}
        </div>
      </section>

      {/* 系统优势 */}
      <section className="bg-white py-16">
        <div className="mx-auto max-w-6xl px-8">
          <div className="mb-8 text-center">
            <h2 className="text-2xl font-bold text-slate-900">系统优势</h2>
            <p className="mt-2 text-sm text-slate-500">
              专业、协同、智能的法律 AI 能力
            </p>
          </div>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {advantages.map((a) => (
              <div
                key={a.title}
                className="rounded-2xl border border-slate-200 bg-slate-50/50 p-6 transition hover:border-blue-200 hover:bg-white hover:shadow-md"
              >
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
            ))}
          </div>
        </div>
      </section>

      {/* 快速开始教程 */}
      <section className="mx-auto max-w-6xl px-8 py-16">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-slate-900">快速开始</h2>
          <p className="mt-2 text-sm text-slate-500">
            四步即可获得专业的法律 AI 服务
          </p>
        </div>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s, idx) => (
            <div key={s.no} className="relative">
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
