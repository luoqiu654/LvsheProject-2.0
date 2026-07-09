// react-syntax-highlighter v16 类型声明
// v16 未自带 TypeScript 声明文件，此处提供最小声明以供 MarkdownRenderer 使用

declare module "react-syntax-highlighter" {
  type ComponentType<T = Record<string, unknown>> =
    import("react").ComponentType<T>
  type ReactNode = import("react").ReactNode
  type CSSProperties = import("react").CSSProperties
  type HTMLAttributes<T = HTMLElement> = import("react").HTMLAttributes<T>

  export interface SyntaxHighlighterProps {
    language?: string
    style?: Record<string, CSSProperties>
    customStyle?: CSSProperties
    customCodeTagProps?: HTMLAttributes<HTMLElement>
    PreTag?: string | ComponentType
    CodeTag?: string | ComponentType
    children?: ReactNode
    showLineNumbers?: boolean
    startingLineNumber?: number
    lineNumberStyle?: CSSProperties
    [key: string]: unknown
  }

  export const Prism: ComponentType<SyntaxHighlighterProps>
  export const Light: ComponentType<SyntaxHighlighterProps>
  export const LightAsync: ComponentType<SyntaxHighlighterProps>
  export const PrismAsync: ComponentType<SyntaxHighlighterProps>
  export const PrismAsyncLight: ComponentType<SyntaxHighlighterProps>
  export const createElement: ComponentType<SyntaxHighlighterProps>
}

declare module "react-syntax-highlighter/dist/esm/styles/prism" {
  type CSSProperties = import("react").CSSProperties

  export const oneDark: Record<string, CSSProperties>
  export const oneLight: Record<string, CSSProperties>
  export const vscDarkPlus: Record<string, CSSProperties>
  export const dracula: Record<string, CSSProperties>
  export const atomOneDark: Record<string, CSSProperties>
  export const atomOneLight: Record<string, CSSProperties>
}

declare module "react-syntax-highlighter/dist/cjs/styles/prism" {
  type CSSProperties = import("react").CSSProperties

  export const oneDark: Record<string, CSSProperties>
  export const oneLight: Record<string, CSSProperties>
  export const vscDarkPlus: Record<string, CSSProperties>
  export const dracula: Record<string, CSSProperties>
  export const atomOneDark: Record<string, CSSProperties>
  export const atomOneLight: Record<string, CSSProperties>
}
