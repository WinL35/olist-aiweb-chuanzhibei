import { AppShell } from "@/components/shell/app-shell";

/**
 * 带侧栏的应用外壳。
 * 所有业务页共享这套导航，切换路由时侧栏不重新挂载。
 */
export default function ShellLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
