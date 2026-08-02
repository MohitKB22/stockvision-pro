"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useMarket } from "@/context/market-context";
import { useQuote } from "@/hooks/use-market-data";
import { useSubmitOrder } from "@/hooks/use-portfolio";
import { useStocks } from "@/hooks/use-stocks";
import { formatCurrency, formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { FieldError, Input, Label } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

/**
 * Order entry.
 *
 * Validation is a Zod schema resolved manually rather than via
 * `@hookform/resolvers` — one fewer dependency for a single form, and the mapping
 * is three lines. Every constraint here mirrors a constraint the API enforces, so
 * the form cannot construct a request the server will reject.
 */
const orderSchema = z.object({
  symbol: z.string().min(1, "Select a symbol"),
  quantity: z.coerce.number().positive("Quantity must be greater than zero"),
  price: z.coerce.number().positive("Price must be greater than zero"),
  transaction_cost: z.coerce.number().min(0, "Cost cannot be negative"),
  notes: z.string().max(500).optional(),
});

/**
 * The FORM shape is all-strings (an <input> always yields a string, even with
 * type="number"); the PARSED shape is coerced numbers. Keeping them as separate
 * types is what stops `string | number` unions leaking into the submit handler and
 * forcing a cast at every field.
 */
interface OrderForm {
  symbol: string;
  quantity: string;
  price: string;
  transaction_cost: string;
  notes: string;
}

export function NewOrderDialog({
  portfolioId,
  trigger,
  defaultSymbol,
}: {
  portfolioId: string;
  trigger: React.ReactNode;
  defaultSymbol?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [side, setSide] = React.useState<"buy" | "sell">("buy");
  const { currencySymbol, grouping } = useMarket();

  const stocksQuery = useStocks();
  const submitOrder = useSubmitOrder(portfolioId);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<OrderForm>({
    defaultValues: {
      symbol: defaultSymbol ?? "",
      quantity: "",
      price: "",
      transaction_cost: "0",
      notes: "",
    },
  });

  const symbol = watch("symbol");
  const quantity = Number(watch("quantity")) || 0;
  const price = Number(watch("price")) || 0;

  const quoteQuery = useQuote(symbol || undefined);

  // Prefill the price with the last traded price when a symbol is chosen. The user
  // can override it — this is a convenience, not a constraint.
  React.useEffect(() => {
    if (quoteQuery.data?.last_price) {
      setValue("price", quoteQuery.data.last_price.toFixed(2));
    }
  }, [quoteQuery.data, setValue]);

  const onSubmit = handleSubmit(async (values) => {
    const parsed = orderSchema.safeParse(values);
    if (!parsed.success) return;

    await submitOrder.mutateAsync({
      symbol: parsed.data.symbol,
      side,
      quantity: parsed.data.quantity,
      price: parsed.data.price,
      transaction_cost: parsed.data.transaction_cost,
      notes: parsed.data.notes || undefined,
    });
    reset();
    setOpen(false);
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record a transaction</DialogTitle>
          <DialogDescription>
            Paper trade — holdings are rebuilt by replaying the full order ledger.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4">
          <Tabs value={side} onValueChange={(value) => setSide(value as "buy" | "sell")}>
            <TabsList className="w-full">
              <TabsTrigger
                value="buy"
                className="flex-1 data-[state=active]:!bg-gain/15 data-[state=active]:!text-gain"
              >
                Buy
              </TabsTrigger>
              <TabsTrigger
                value="sell"
                className="flex-1 data-[state=active]:!bg-loss/15 data-[state=active]:!text-loss"
              >
                Sell
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <div>
            <Label htmlFor="order-symbol">Symbol</Label>
            <Select value={symbol} onValueChange={(value) => setValue("symbol", value)}>
              <SelectTrigger id="order-symbol" className="mt-1">
                <SelectValue placeholder="Select a stock" />
              </SelectTrigger>
              <SelectContent>
                {(stocksQuery.data ?? []).map((stock) => (
                  <SelectItem key={stock.id} value={stock.symbol}>
                    {stock.symbol} — {stock.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError>{errors.symbol?.message}</FieldError>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="order-quantity">Quantity</Label>
              <Input
                id="order-quantity"
                type="number"
                step="any"
                min="0"
                className="mt-1"
                invalid={Boolean(errors.quantity)}
                {...register("quantity")}
              />
              <FieldError>{errors.quantity?.message}</FieldError>
            </div>
            <div>
              <Label htmlFor="order-price">Price ({currencySymbol})</Label>
              <Input
                id="order-price"
                type="number"
                step="any"
                min="0"
                className="mt-1"
                invalid={Boolean(errors.price)}
                {...register("price")}
              />
              <FieldError>{errors.price?.message}</FieldError>
              {quoteQuery.data ? (
                <p className="mt-1 text-2xs text-ink-faint">
                  LTP {formatNumber(quoteQuery.data.last_price, { grouping })}
                </p>
              ) : null}
            </div>
          </div>

          <div>
            <Label htmlFor="order-cost">Transaction cost (brokerage, fees)</Label>
            <Input
              id="order-cost"
              type="number"
              step="any"
              min="0"
              className="mt-1"
              {...register("transaction_cost")}
            />
          </div>

          <div>
            <Label htmlFor="order-notes">Notes (optional)</Label>
            <Input
              id="order-notes"
              className="mt-1"
              placeholder="Rationale for this trade"
              {...register("notes")}
            />
          </div>

          <div className="rounded-lg border border-line bg-elevated/50 px-3 py-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-ink-subtle">Order value</span>
              <span className="tabular font-medium text-ink">
                {formatCurrency(quantity * price, { symbol: currencySymbol, grouping })}
              </span>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant={side === "buy" ? "success" : "danger"}
              loading={submitOrder.isPending}
            >
              {side === "buy" ? "Record buy" : "Record sell"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
