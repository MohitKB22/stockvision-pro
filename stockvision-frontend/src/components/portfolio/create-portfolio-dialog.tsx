"use client";

import * as React from "react";
import { useForm } from "react-hook-form";

import { useMarket } from "@/context/market-context";
import { useCreatePortfolio } from "@/hooks/use-portfolio";
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

interface CreatePortfolioForm {
  name: string;
  cash_balance: string;
}

export function CreatePortfolioDialog({ trigger }: { trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const { definition, currencySymbol } = useMarket();
  const createPortfolio = useCreatePortfolio();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreatePortfolioForm>({ defaultValues: { name: "", cash_balance: "0" } });

  const onSubmit = handleSubmit(async (values) => {
    await createPortfolio.mutateAsync({
      name: values.name.trim(),
      cash_balance: Number(values.cash_balance) || 0,
    });
    reset();
    setOpen(false);
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Create portfolio</DialogTitle>
          <DialogDescription>
            Currency and benchmark are set automatically from the selected market
            {definition ? ` (${definition.currency}, ${definition.benchmark_symbol})` : ""}.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <Label htmlFor="portfolio-name">Name</Label>
            <Input
              id="portfolio-name"
              className="mt-1"
              placeholder="Long-term growth"
              invalid={Boolean(errors.name)}
              {...register("name", { required: "A name is required", maxLength: 255 })}
            />
            <FieldError>{errors.name?.message}</FieldError>
          </div>

          <div>
            <Label htmlFor="portfolio-cash">Opening cash balance ({currencySymbol})</Label>
            <Input
              id="portfolio-cash"
              type="number"
              step="any"
              min="0"
              className="mt-1"
              {...register("cash_balance")}
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={createPortfolio.isPending}>
              Create portfolio
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
