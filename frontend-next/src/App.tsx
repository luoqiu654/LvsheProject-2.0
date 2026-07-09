import { Routes, Route, Outlet } from "react-router-dom"
import { Sidebar } from "@/components/layout/Sidebar"
import { TopBar } from "@/components/layout/TopBar"
import Home from "@/pages/Home"
import Chat from "@/pages/Chat"
import Contract from "@/pages/Contract"
import Expert from "@/pages/Expert"
import MapView from "@/pages/MapView"
import Relax from "@/pages/Relax"

// 主布局：左侧导航 + 右侧内容区（Outlet 渲染子路由）
function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

// 根组件：路由配置
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="chat" element={<Chat />} />
        <Route path="contract" element={<Contract />} />
        <Route path="expert" element={<Expert />} />
        <Route path="map" element={<MapView />} />
        <Route path="relax" element={<Relax />} />
      </Route>
    </Routes>
  )
}
