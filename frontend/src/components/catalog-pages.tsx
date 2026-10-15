import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, ArrowUpRight, FlaskConical, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { METRICS, metricText } from "@/lib/strategy";
import { FACTOR_INFO, request, validateStrategy, type ParameterValue, type Strategy } from "@/lib/catalog";

function PageTitle({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <header className="space-y-3"><p className="text-xs tracking-[0.2em] text-primary">{eyebrow}</p><h1 className="text-3xl font-semibold tracking-tight">{title}</h1><p className="max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p></header>;
}

export function FactorsPage({ id }: { id?: string }) {
  const factor = METRICS.find((item) => item.key === id);
  if (id && !factor) return <NotFound />;
  if (factor) {
    const info = FACTOR_INFO[factor.key];
    return <div className="space-y-6"><Back href="/factors" label="全部因子" /><PageTitle eyebrow="FACTOR DETAIL" title={factor.label} description={info.description} />
      <Card className="p-6 shadow-none"><h2 className="font-semibold">计算方式</h2><p className="mono rounded-lg bg-secondary p-5 text-sm">{info.formula}</p><p className="text-sm leading-6 text-muted-foreground">{info.note}</p></Card>
      <Card className="p-6 shadow-none"><h2 className="font-semibold">使用说明</h2><p className="text-sm text-muted-foreground">展示单位：{factor.unit}。{factor.scale === 100 ? "策略阈值以比例输入，0.05 表示 5%。" : "策略阈值以倍数输入。"} 缺失指标不会通过依赖它的筛选条件。</p><a href="/strategies" className="text-sm text-primary">查看策略如何使用因子 →</a></Card>
    </div>;
  }
  return <div className="space-y-6"><PageTitle eyebrow="FACTOR LIBRARY" title="因子库" description="从价格、风险与成交量理解市场。查看现有因子的计算口径，再选择适合策略的筛选条件。" />
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{METRICS.map((item) => <a key={item.key} href={`/factors/${item.key}`} className="group"><Card className="h-full p-6 shadow-none transition-colors group-hover:border-primary"><div className="flex items-center justify-between"><span className="rounded-md bg-secondary px-2 py-1 text-xs text-muted-foreground">{item.unit}</span><ArrowUpRight size={17} className="text-muted-foreground group-hover:text-primary" /></div><h2 className="font-semibold">{item.label}</h2><p className="text-sm leading-6 text-muted-foreground">{FACTOR_INFO[item.key].description}</p><p className="mono text-xs text-muted-foreground">{item.key}</p></Card></a>)}</div>
  </div>;
}

const optionLabels: Record<string, string> = { baostock: "BaoStock", tushare: "Tushare", none: "不复权", qfq: "前复权", hfq: "后复权", "sh.000300": "沪深 300", "sh.000001": "上证指数", "sz.399001": "深证成指", "sz.399006": "创业板指", "sh.000016": "上证 50", "sh.000905": "中证 500" };

export function StrategiesPage({ id }: { id?: string }) {
  const [items, setItems] = useState<Strategy[]>([]);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [values, setValues] = useState<Record<string, ParameterValue>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setStrategy(null); setMessage(""); setDirty(false);
    const load = async () => {
      try {
        if (id) {
          const loaded = validateStrategy(await request<Strategy>(`/api/strategies/${encodeURIComponent(id)}`, { signal: controller.signal }));
          setStrategy(loaded); setValues(loaded.parameters);
        } else {
          setItems((await request<Strategy[]>("/api/strategies", { signal: controller.signal })).map(validateStrategy));
        }
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "策略加载失败。");
      } finally { if (!controller.signal.aborted) setLoading(false); }
    };
    void load();
    return () => controller.abort();
  }, [id, retry]);

  async function preview(event: FormEvent) {
    event.preventDefault(); if (!strategy) return;
    setSaving(true); setError(""); setMessage("");
    try {
      const loaded = validateStrategy(await request<Strategy>(`/api/strategies/${encodeURIComponent(strategy.id)}/preview`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values),
      }));
      setStrategy(loaded); setValues(loaded.parameters); setDirty(false); setMessage("参数已校验，下面的筛选规则已更新。本次调整仅用于当前页面预览。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "参数校验失败。"); }
    finally { setSaving(false); }
  }

  return <div className="space-y-6">
    {id && <Back href="/strategies" label="全部策略" />}
    <PageTitle eyebrow={id ? "STRATEGY DETAIL" : "STRATEGY LIBRARY"} title={strategy?.definition.name ?? (id ? "策略详情" : "策略库")} description={strategy?.description ?? "策略把因子组合成选股条件，用于筛选和排序股票。选择一种策略，了解它的逻辑，再调整参数、预览规则。"} />
    <Card className="p-6 shadow-none"><h2 className="font-semibold">策略用来做什么？</h2><p className="text-sm leading-6 text-muted-foreground">因子衡量股票的某个特征，策略决定用哪些因子、设置什么条件，以及入选后如何排序。例如，动量策略可以要求区间收益为正、价格高于 20 日均线，再按收益从高到低排列。</p><p className="text-sm leading-6 text-muted-foreground">当前页面用于了解策略、调整参数和预览筛选规则。点击“校验并预览规则”只会更新规则，不会生成选股结果。动量策略已提供独立的周调仓研究回测，页面参数暂不用于回测。</p></Card>
    {loading && <Card role="status" className="p-8 text-sm text-muted-foreground">正在加载策略…</Card>}
    {error && <Card role="alert" className="p-5 shadow-none"><p className="whitespace-pre-wrap text-sm text-destructive">{error}</p>{!strategy && <Button variant="outline" onClick={() => setRetry((value) => value + 1)}><RefreshCw size={14} />重试</Button>}</Card>}
    {!loading && !id && !error && <div className="grid gap-4 lg:grid-cols-3">{items.map((item, index) => <a href={`/strategies/${item.id}`} key={item.id} className="group"><Card className="h-full p-6 shadow-none transition-colors group-hover:border-primary"><div className="flex justify-between"><span className="mono text-xs text-primary">0{index + 1} / SCREENING</span><ArrowUpRight size={17} className="text-muted-foreground" /></div><h2 className="text-xl font-semibold">{item.definition.name}</h2><p className="text-sm leading-6 text-muted-foreground">{item.description}</p><div className="mt-auto flex gap-3 border-t pt-4 text-xs text-muted-foreground"><span>{item.definition.conditions.length} 条规则</span><span>参数可选</span></div></Card></a>)}</div>}
    {strategy && <div className="grid items-start gap-5 xl:grid-cols-[1.1fr_1fr]">
      <Card className="p-6 shadow-none"><h2 className="font-semibold">策略参数</h2><p className="text-xs text-muted-foreground">选择时间范围与阈值，校验后更新规则预览。比例输入 0.05 表示 5%。</p>
        <form onSubmit={(event) => void preview(event)} className="space-y-5"><fieldset disabled={saving} className="grid gap-4 sm:grid-cols-2">{Object.entries(strategy.parameter_schema.properties).map(([key, schema]) => {
          const choices = schema.enum ?? schema.anyOf?.find((item) => item.enum)?.enum;
          const nullable = schema.anyOf?.some((item) => item.type === "null");
          const update = (value: ParameterValue) => { setValues((previous) => ({ ...previous, [key]: value })); setDirty(true); setMessage(""); };
          const control = "mt-2 h-10 w-full rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30";
          return <label key={key} className="text-sm">{schema.title}{choices ? <select aria-label={schema.title} className={control} value={String(values[key] ?? "")} onChange={(event) => update(event.target.value || null)}>{nullable && <option value="">无基准</option>}{choices.map((value) => <option key={String(value)} value={value ?? ""}>{value === null ? "无基准" : optionLabels[value] ?? value}</option>)}</select> : <input aria-label={schema.title} className={control} type={schema.format === "date" ? "date" : "number"} step={schema.type === "number" ? "any" : undefined} min={schema.minimum} max={schema.maximum} required value={values[key] ?? ""} onChange={(event) => update(schema.type === "number" ? (event.target.value === "" ? "" : Number(event.target.value)) : event.target.value)} />}</label>;
        })}</fieldset><div className="flex flex-wrap items-center gap-3"><Button type="submit" disabled={saving}>{saving ? "正在校验…" : "校验并预览规则"}</Button><span className="text-xs text-muted-foreground">{dirty ? "有未校验的修改" : "当前参数已校验"}</span></div></form>
        {message && <p role="status" className="text-sm leading-6 text-primary">{message}</p>}
      </Card>
      <div className="space-y-5"><Card className="p-6 shadow-none"><h2 className="font-semibold">筛选逻辑{dirty ? " · 上次校验" : ""}</h2><p className="text-xs text-muted-foreground">所有条件同时满足才入选。{strategy.definition.start_date} 至 {strategy.definition.end_date}</p>{strategy.definition.conditions.map((rule, index) => <div key={index} className="flex flex-wrap justify-between gap-2 border-t pt-4 text-sm"><a className="text-primary" href={`/factors/${rule.metric}`}>{METRICS.find((metric) => metric.key === rule.metric)?.label}</a><span className="mono">{rule.operator === "gte" ? "≥" : "≤"} {metricText(rule.metric, rule.value)}</span></div>)}<p className="border-t pt-4 text-xs text-muted-foreground">排序：{METRICS.find((metric) => metric.key === strategy.definition.sort_by)?.label} · {strategy.definition.sort_direction === "asc" ? "从低到高" : "从高到低"}</p></Card>
      </div>
    </div>}
  </div>;
}

export function BacktestsPage({ id }: { id?: string }) {
  if (id) return <NotFound title="未找到回测记录" description="目前还没有生成回测记录。" href="/backtests" />;
  return <div className="space-y-6"><PageTitle eyebrow="BACKTEST LAB" title="回测" description="在历史行情中检验策略。后续将在这里管理回测任务，比较收益、风险与交易表现。" />
    <Card className="items-center p-12 text-center shadow-none"><div className="rounded-full bg-secondary p-4 text-primary"><FlaskConical size={28} /></div><h2 className="text-xl font-semibold">回测页面待接入</h2><p className="max-w-md text-sm leading-6 text-muted-foreground">动量策略已支持周调仓研究回测，可通过后端接口运行并查看指标、每日资产和交易记录。此页面暂不保存或展示回测结果。</p><a href="/strategies" className="mt-2 text-sm font-medium text-primary">先查看策略 →</a></Card>
  </div>;
}

export function NotFound({ title = "页面不存在", description = "请检查地址，或返回列表继续浏览。", href = "/strategies" }: { title?: string; description?: string; href?: string }) {
  return <Card className="items-center p-12 text-center shadow-none"><h1 className="text-2xl font-semibold">{title}</h1><p className="text-sm text-muted-foreground">{description}</p><a href={href} className="text-sm text-primary">返回列表 →</a></Card>;
}

function Back({ href, label }: { href: string; label: string }) {
  return <a href={href} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-primary"><ArrowLeft size={15} />{label}</a>;
}
