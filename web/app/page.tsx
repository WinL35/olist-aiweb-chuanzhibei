import { redirect } from "next/navigation";

/** 根路径直达经营看板 */
export default function Home() {
  redirect("/dashboard");
}
