import axios from "axios"

// axios 实例，baseURL 留空走 vite proxy（/api → 后端）
const client = axios.create({
  baseURL: "",
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
})

// 请求拦截器：可在此附加 token 等通用请求头
client.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：统一错误处理
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error?.response?.data?.detail || error?.message || "请求失败"
    console.error("[API Error]", message)
    return Promise.reject(error)
  },
)

export default client
