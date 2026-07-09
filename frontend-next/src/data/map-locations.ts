/**
 * 地图地点数据 - 可迭代扩展
 * ====================================================================
 * 开发者指南（如何添加新地点）：
 *
 * 1. 在下方 `mapLocations` 数组中追加一个对象即可，例如：
 *
 *    {
 *      id: 'loc-unique-id',            // 唯一ID，建议使用 loc- 前缀
 *      name: 'XX律师事务所',             // 显示名称
 *      category: 'law_firm',           // 类别（见下方 LocationCategory）
 *      address: '上海市XX区XX路XX号',    // 详细地址
 *      lat: 31.2304,                   // 纬度
 *      lng: 121.4737,                  // 经度
 *      phone: '021-XXXXXXXX',          // 联系电话（可选，可空字符串）
 *      description: '律所简介...',      // 描述（可选）
 *    }
 *
 * 2. 类别取值范围（LocationCategory）：
 *    - "law_firm"        律所
 *    - "court"           法院
 *    - "police"          警察局
 *    - "labor_bureau"     劳务派遣管理局
 *    - "other"           其他
 *
 * 3. 如需新增类别：
 *    - 在 `LocationCategory` 类型中追加字面量
 *    - 在 `categoryConfig` 中追加对应配置（颜色/图标/中文名）
 *    - 即可在面板筛选与地图标记中自动生效
 * ====================================================================
 */

/** 地点类别 */
export type LocationCategory =
  | 'law_firm'
  | 'court'
  | 'police'
  | 'labor_bureau'
  | 'other'

/** 地点数据结构 */
export interface MapLocation {
  /** 唯一ID */
  id: string
  /** 显示名称 */
  name: string
  /** 类别 */
  category: LocationCategory
  /** 详细地址 */
  address: string
  /** 纬度 */
  lat: number
  /** 经度 */
  lng: number
  /** 联系电话（可空） */
  phone?: string
  /** 描述（可空） */
  description?: string
}

/** 类别配置：颜色 / 图标 / 中文名 */
export interface CategoryConfig {
  /** 中文标签 */
  label: string
  /** 标记主色（hex，用于地图 marker 与面板） */
  color: string
  /** 标记描边色 */
  borderColor: string
  /** lucide 图标名（与 LocationPanel 中图标映射对应） */
  icon: 'scale' | 'gavel' | 'shield' | 'briefcase' | 'map-pin'
}

/** 类别 -> 配置映射 */
export const categoryConfig: Record<LocationCategory, CategoryConfig> = {
  law_firm: {
    label: '律所',
    color: '#3B82F6', // blue-500
    borderColor: '#1D4ED8',
    icon: 'scale',
  },
  court: {
    label: '法院',
    color: '#A855F7', // purple-500
    borderColor: '#7E22CE',
    icon: 'gavel',
  },
  police: {
    label: '警察局',
    color: '#EF4444', // red-500
    borderColor: '#B91C1C',
    icon: 'shield',
  },
  labor_bureau: {
    label: '劳务派遣管理局',
    color: '#F59E0B', // amber-500
    borderColor: '#B45309',
    icon: 'briefcase',
  },
  other: {
    label: '其他',
    color: '#10B981', // emerald-500
    borderColor: '#047857',
    icon: 'map-pin',
  },
}

/** 所有类别（用于面板筛选顺序） */
export const allCategories: LocationCategory[] = [
  'law_firm',
  'court',
  'police',
  'labor_bureau',
  'other',
]

/**
 * 地点示例数据（上海地区）
 * 后续可在此数组中自由追加，无需修改任何组件代码。
 */
export const mapLocations: MapLocation[] = [
  {
    id: 'loc-001',
    name: '上海市第一中级人民法院',
    category: 'court',
    address: '上海市浦东新区世纪大道 1588 号',
    lat: 31.2304,
    lng: 121.5456,
    phone: '021-58692000',
    description: '管辖浦东新区、闵行区、南汇区等区域的一审、二审案件。',
  },
  {
    id: 'loc-002',
    name: '上海市浦东新区人民法院',
    category: 'court',
    address: '上海市浦东新区惠南镇城南路 55 号',
    lat: 31.0386,
    lng: 121.7589,
    phone: '021-58028000',
    description: '浦东新区基层人民法院，审理辖区内民事、刑事、行政一审案件。',
  },
  {
    id: 'loc-003',
    name: '锦天城律师事务所（总部）',
    category: 'law_firm',
    address: '上海市浦东新区银城路 501 号上海中心大厦 11/12 层',
    lat: 31.2358,
    lng: 121.5064,
    phone: '021-20580000',
    description: '全国知名综合性律师事务所，提供公司、金融、争议解决等全领域法律服务。',
  },
  {
    id: 'loc-004',
    name: '上海市君悦律师事务所',
    category: 'law_firm',
    address: '上海市静安区南京西路 1601 号越洋广场 8 楼',
    lat: 31.2261,
    lng: 121.4542,
    phone: '021-61359600',
    description: '专注于公司商事、房地产、知识产权等领域的综合律师事务所。',
  },
  {
    id: 'loc-005',
    name: '上海市公安局浦东分局',
    category: 'police',
    address: '上海市浦东新区杨高中路 3188 号',
    lat: 31.2228,
    lng: 121.5789,
    phone: '021-50680110',
    description: '浦东新区公安分局，负责辖区治安管理、刑事案件侦查。',
  },
  {
    id: 'loc-006',
    name: '上海市公安局黄浦分局',
    category: 'police',
    address: '上海市黄浦区建国东路 380 号',
    lat: 31.2167,
    lng: 121.4833,
    phone: '021-63280110',
    description: '黄浦区公安分局，负责辖区治安管理与刑事侦查。',
  },
  {
    id: 'loc-007',
    name: '浦东新区人力资源和社会保障局',
    category: 'labor_bureau',
    address: '上海市浦东新区世纪大道 2001 号',
    lat: 31.2295,
    lng: 121.5388,
    phone: '021-58787799',
    description: '负责辖区劳动就业、社保、劳动争议调解与劳务派遣管理。',
  },
  {
    id: 'loc-008',
    name: '上海市劳动保障监察总队',
    category: 'labor_bureau',
    address: '上海市黄浦区中山南路 1088 号',
    lat: 31.2156,
    lng: 121.4901,
    phone: '021-63680110',
    description: '负责全市劳动保障监察执法，处理拖欠工资、违法用工等投诉。',
  },
  {
    id: 'loc-009',
    name: '方达律师事务所（上海办公室）',
    category: 'law_firm',
    address: '上海市静安区石门一路 288 号兴业太古汇香港兴业中心二座 22 楼',
    lat: 31.2351,
    lng: 121.4623,
    phone: '021-22081166',
    description: '国内领先商事律所，专注跨境并购、争议解决、金融监管。',
  },
  {
    id: 'loc-010',
    name: '上海市法律援助中心',
    category: 'other',
    address: '上海市徐汇区小木桥路 268 号',
    lat: 31.1899,
    lng: 121.4567,
    phone: '021-64189500',
    description: '为经济困难群众提供免费法律咨询与援助，受理法律援助申请。',
  },
]
