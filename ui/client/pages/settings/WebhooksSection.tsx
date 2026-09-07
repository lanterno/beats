import { Plus, Trash2, Webhook } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { del, get, post } from "@/shared/api";

export interface WebhookEntry {
	id: string;
	url: string;
	events: string[];
	active: boolean;
}

export function WebhooksSection() {
	const [webhooks, setWebhooks] = useState<WebhookEntry[]>([]);
	const [newUrl, setNewUrl] = useState("");
	const [adding, setAdding] = useState(false);

	const loadWebhooks = useCallback(async () => {
		try {
			const data = await get<WebhookEntry[]>("/api/webhooks/");
			setWebhooks(data);
		} catch {
			// ignore if endpoint not available
		}
	}, []);

	useEffect(() => {
		loadWebhooks();
	}, [loadWebhooks]);

	const handleAdd = async () => {
		if (!newUrl.trim()) return;
		setAdding(true);
		try {
			await post("/api/webhooks/", { url: newUrl.trim() });
			setNewUrl("");
			await loadWebhooks();
			toast.success("Webhook added");
		} catch {
			toast.error("Failed to add webhook");
		} finally {
			setAdding(false);
		}
	};

	const handleDelete = async (id: string) => {
		try {
			await del(`/api/webhooks/${id}`);
			await loadWebhooks();
			toast("Webhook removed");
		} catch {
			toast.error("Failed to remove webhook");
		}
	};

	return (
		<section className="mb-8">
			<h2 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
				<Webhook className="w-4 h-4 text-accent" />
				Webhooks
			</h2>
			<div className="rounded-lg border border-border/80 bg-card shadow-soft p-4 space-y-3">
				<p className="text-xs text-muted-foreground">
					Receive POST requests on <code className="text-foreground/80">timer.start</code> and{" "}
					<code className="text-foreground/80">timer.stop</code> events. Works with IFTTT, Zapier,
					Home Assistant, or custom endpoints.
				</p>

				{webhooks.length > 0 && (
					<div className="space-y-1.5">
						{webhooks.map((wh) => (
							<div
								key={wh.id}
								className="flex items-center gap-2 bg-secondary/30 rounded px-2.5 py-1.5"
							>
								<code className="text-xs text-foreground/80 font-mono truncate flex-1">
									{wh.url}
								</code>
								<span className="text-[10px] text-muted-foreground shrink-0">
									{wh.events.join(", ")}
								</span>
								<button
									type="button"
									onClick={() => handleDelete(wh.id)}
									className="p-1 text-muted-foreground/40 hover:text-destructive transition-colors shrink-0"
								>
									<Trash2 className="w-3 h-3" />
								</button>
							</div>
						))}
					</div>
				)}

				<div className="flex gap-2">
					<input
						type="url"
						value={newUrl}
						onChange={(e) => setNewUrl(e.target.value)}
						placeholder="https://example.com/webhook"
						onKeyDown={(e) => e.key === "Enter" && handleAdd()}
						className="flex-1 text-xs bg-secondary/50 border border-border rounded px-2.5 py-1.5 text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-accent font-mono"
					/>
					<button
						type="button"
						onClick={handleAdd}
						disabled={!newUrl.trim() || adding}
						className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-accent-foreground disabled:opacity-40 hover:bg-accent/85 transition-colors"
					>
						<Plus className="w-3 h-3" />
						Add
					</button>
				</div>
			</div>
		</section>
	);
}
