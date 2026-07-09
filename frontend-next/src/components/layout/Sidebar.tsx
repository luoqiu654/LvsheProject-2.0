import { Link, useLocation } from "react-router-dom"
import {
  Home,
  MessageSquare,
  FileText,
  Scale,
  Map,
  Heart,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"

// 左侧导航项
interface NavItem {
  to: string
  label: string
  icon: LucideIcon
}

const navItems: NavItem[] = [
  { to: "/", label: "首页", icon: Home },
  { to: "/chat", label: "智能咨询", icon: MessageSquare },
  { to: "/contract", label: "合同诊疗", icon: FileText },
  { to: "/expert", label: "专家会诊", icon: Scale },
  { to: "/map", label: "地图浏览", icon: Map },
  { to: "/relax", label: "放松模式", icon: Heart },
]

// 左侧导航栏
export function Sidebar() {
  const location = useLocation()

  return (
    <aside className="flex w-60 shrink-0 flex-col bg-slate-900 text-slate-200">
      <div className="flex h-16 items-center border-b border-slate-800 px-6">
        <span className="text-lg font-semibold text-white">LvsheProject</span>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const active =
            item.to === "/"
              ? location.pathname === "/"
              : location.pathname.startsWith(item.to)
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-blue-600 text-white"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white",
              )}
            >
              <item.icon className="h-4 w-4" />
              <span>{item.label}</span>
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
