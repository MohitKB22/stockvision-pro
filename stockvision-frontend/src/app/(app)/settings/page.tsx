"use client";

import * as React from "react";
import { Check, KeyRound, Palette, RotateCcw, Sliders, X } from "lucide-react";

import { useMarket } from "@/context/market-context";
import {
  useIntegrations,
  useResetSettings,
  useSettings,
  useUpdateSettings,
} from "@/hooks/use-platform";
import type { AppSettings, MarketCode } from "@/types";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/input";
import { Separator, Switch } from "@/components/ui/misc";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkeletonText } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState } from "@/components/ui/states";

const NOTIFICATION_SETTINGS = [
  ["market_alerts", "Market alerts", "Index moves and unusual breadth."],
  ["signal_alerts", "AI signal alerts", "When a new BUY/SELL signal is generated."],
  ["price_alerts", "Price alerts", "When a watchlist alert threshold is crossed."],
  ["email_notifications", "Email notifications", "Send the above to your email address."],
  ["push_notifications", "Push notifications", "Browser push for time-sensitive alerts."],
  ["weekly_digest", "Weekly digest", "A Monday summary of portfolio and market activity."],
] as const;

/**
 * Settings.
 *
 * Preferences are persisted server-side, so they survive a cache clear and are
 * shared across devices. Every toggle writes immediately (no Save button): the
 * mutation writes the server's response straight into the cache, so a switch never
 * visually snaps back while a request is in flight.
 */
export default function SettingsPage() {
  const settingsQuery = useSettings();
  const integrationsQuery = useIntegrations();
  const updateSettings = useUpdateSettings();
  const resetSettings = useResetSettings();
  const { setMarket } = useMarket();

  const settings = settingsQuery.data;

  const patch = React.useCallback(
    (changes: Partial<AppSettings>) => {
      updateSettings.mutate(changes);
      // Keep the in-session market switcher in step with the saved default.
      if (changes.default_market) setMarket(changes.default_market as MarketCode);
    },
    [updateSettings, setMarket],
  );

  if (settingsQuery.isLoading) {
    return (
      <div className="space-y-5">
        <PageHeader title="Settings" description="Preferences, integrations and appearance" />
        <Card>
          <CardContent className="pt-5">
            <SkeletonText lines={10} />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (settingsQuery.isError || !settings) {
    return (
      <div className="space-y-5">
        <PageHeader title="Settings" />
        <Card>
          <CardContent className="pt-5">
            <ErrorState error={settingsQuery.error} onRetry={() => settingsQuery.refetch()} />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Settings"
        description="Preferences are stored on the server and apply everywhere you open the app"
        actions={
          <Button
            variant="outline"
            size="sm"
            loading={resetSettings.isPending}
            onClick={() => resetSettings.mutate()}
          >
            <RotateCcw aria-hidden /> Restore defaults
          </Button>
        }
      />

      <Tabs defaultValue="general">
        <TabsList className="flex-wrap">
          <TabsTrigger value="general">
            <Sliders aria-hidden /> General
          </TabsTrigger>
          <TabsTrigger value="appearance">
            <Palette aria-hidden /> Appearance
          </TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
          <TabsTrigger value="integrations">
            <KeyRound aria-hidden /> Integrations
          </TabsTrigger>
        </TabsList>

        <TabsContent value="general">
          <Card>
            <CardHeader>
              <CardTitle>General</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <SettingRow label="Language" description="Interface language.">
                <Select
                  value={settings.language}
                  onValueChange={(value) => patch({ language: value })}
                >
                  <SelectTrigger className="w-[184px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="hi">हिन्दी (Hindi)</SelectItem>
                    <SelectItem value="ta">தமிழ் (Tamil)</SelectItem>
                  </SelectContent>
                </Select>
              </SettingRow>

              <Separator />

              <SettingRow label="Default market" description="Which market the app opens with.">
                <Select
                  value={settings.default_market}
                  onValueChange={(value) => patch({ default_market: value as MarketCode })}
                >
                  <SelectTrigger className="w-[184px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="IN">India (NSE)</SelectItem>
                    <SelectItem value="US">United States</SelectItem>
                  </SelectContent>
                </Select>
              </SettingRow>

              <Separator />

              <SettingRow
                label="Number format"
                description="Auto follows the market — Indian lakh/crore grouping for NSE, western grouping for US."
              >
                <Select
                  value={settings.number_format}
                  onValueChange={(value) =>
                    patch({ number_format: value as AppSettings["number_format"] })
                  }
                >
                  <SelectTrigger className="w-[184px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto (follow market)</SelectItem>
                    <SelectItem value="indian">Indian (12,45,000)</SelectItem>
                    <SelectItem value="western">Western (1,245,000)</SelectItem>
                  </SelectContent>
                </Select>
              </SettingRow>

              <Separator />

              <SettingRow
                label="Default landing page"
                description="Where the app opens after launch."
              >
                <Select
                  value={settings.default_dashboard}
                  onValueChange={(value) => patch({ default_dashboard: value })}
                >
                  <SelectTrigger className="w-[184px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["dashboard", "market", "portfolio", "watchlist"].map((page) => (
                      <SelectItem key={page} value={page}>
                        {page.charAt(0).toUpperCase() + page.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </SettingRow>

              <Separator />

              <SettingRow
                label="Auto-refresh interval"
                description="How often live views poll for new data."
              >
                <Select
                  value={String(settings.auto_refresh_seconds)}
                  onValueChange={(value) => patch({ auto_refresh_seconds: Number(value) })}
                >
                  <SelectTrigger className="w-[184px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">Off</SelectItem>
                    <SelectItem value="15">15 seconds</SelectItem>
                    <SelectItem value="30">30 seconds</SelectItem>
                    <SelectItem value="60">1 minute</SelectItem>
                    <SelectItem value="300">5 minutes</SelectItem>
                  </SelectContent>
                </Select>
              </SettingRow>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="appearance">
          <Card>
            <CardHeader>
              <CardTitle>Appearance</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <SettingRow
                label="Theme"
                description="This platform is dark-only by design — a trading interface read for hours is materially harder on the eyes in light mode."
              >
                <Select
                  value={settings.theme}
                  onValueChange={(value) => patch({ theme: value as AppSettings["theme"] })}
                >
                  <SelectTrigger className="w-[184px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="dark">Dark</SelectItem>
                    <SelectItem value="midnight">Midnight (deeper)</SelectItem>
                  </SelectContent>
                </Select>
              </SettingRow>

              <Separator />

              <SettingRow
                label="Default chart type"
                description="Applies to price charts on stock detail pages."
              >
                <Select
                  value={settings.chart_type}
                  onValueChange={(value) =>
                    patch({ chart_type: value as AppSettings["chart_type"] })
                  }
                >
                  <SelectTrigger className="w-[184px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="area">Area</SelectItem>
                    <SelectItem value="line">Line</SelectItem>
                    <SelectItem value="candlestick">Candlestick</SelectItem>
                  </SelectContent>
                </Select>
              </SettingRow>

              <Separator />

              <SettingRow
                label="Reduce motion"
                description="Disables chart entry animations and transitions. Your OS setting is already respected automatically; this forces it on."
              >
                <Switch
                  checked={settings.reduced_motion}
                  onCheckedChange={(checked) => patch({ reduced_motion: checked })}
                  aria-label="Reduce motion"
                />
              </SettingRow>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Notifications</CardTitle>
                <p className="mt-0.5 text-2xs text-ink-faint">
                  These preferences are persisted and read by the alerting layer. Delivery channels
                  (email, push) require an SMTP or push provider to be configured in deployment.
                </p>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              {NOTIFICATION_SETTINGS.map(([key, label, description], index) => (
                <React.Fragment key={key}>
                  <SettingRow label={label} description={description}>
                    <Switch
                      checked={settings[key]}
                      onCheckedChange={(checked) =>
                        patch({ [key]: checked } as Partial<AppSettings>)
                      }
                      aria-label={label}
                    />
                  </SettingRow>
                  {index < NOTIFICATION_SETTINGS.length - 1 ? <Separator /> : null}
                </React.Fragment>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="integrations">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>API Keys &amp; Integrations</CardTitle>
                <p className="mt-0.5 text-2xs text-ink-faint">
                  Keys are supplied through environment variables and are never readable through
                  this interface — not even masked. This page reports connection status only.
                </p>
              </div>
            </CardHeader>
            <CardContent>
              {integrationsQuery.isLoading ? (
                <SkeletonText lines={6} />
              ) : (
                <ul className="space-y-3">
                  {(integrationsQuery.data ?? []).map((integration) => (
                    <li
                      key={integration.provider}
                      className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-line bg-elevated/40 px-4 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-2 text-xs font-medium text-ink">
                          {integration.label}
                          <Badge variant={integration.configured ? "gain" : "default"}>
                            {integration.configured ? (
                              <>
                                <Check className="size-2.5" aria-hidden /> Connected
                              </>
                            ) : (
                              <>
                                <X className="size-2.5" aria-hidden /> Not configured
                              </>
                            )}
                          </Badge>
                        </p>
                        <p className="mt-1 text-2xs leading-relaxed text-ink-subtle">
                          {integration.description}
                        </p>
                      </div>
                      <code className="rounded-md border border-line bg-canvas px-2 py-1 font-mono text-2xs text-ink-faint">
                        {integration.provider.toUpperCase()}_API_KEY
                      </code>
                    </li>
                  ))}
                </ul>
              )}
              <p className="bg-info/8 mt-4 rounded-lg border border-info/25 px-3 py-2 text-2xs leading-relaxed text-info">
                Set these in <code className="font-mono">stockvision-backend/.env</code> and restart
                the API. Without an LLM key the AI Copilot still works — it falls back to a
                clearly-labelled extractive mode that returns the most relevant retrieved passages
                verbatim.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 max-w-md">
        <Label className="text-xs font-medium text-ink">{label}</Label>
        {description ? (
          <p className="mt-1 text-2xs leading-relaxed text-ink-subtle">{description}</p>
        ) : null}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
