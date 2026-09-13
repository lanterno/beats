import { Plus, Trash2, Webhook } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { del, get, post } from "@/shared/api";
import { Button, Panel } from "@/shared/ui";
import { FIELD, HEADING, HEADING_ICON, LEAD, LIST, REMOVE, ROW } from "./styles";

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
			<h2 className={HEADING}>
				<Webhook className={HEADING_ICON} />
				Webhooks
			</h2>
			<Panel padding="p-5" className="space-y-3">
				<p className={LEAD}>
					Receive POST requests on <code className="font-code text-foreground">timer.start</code>{" "}
					and <code className="font-code text-foreground">timer.stop</code> events. Works with
					IFTTT, Zapier, Home Assistant, or custom endpoints.
				</p>

				{webhooks.length > 0 && (
					<div className={LIST}>
						{webhooks.map((wh) => (
							<div key={wh.id} className={ROW}>
								<code className="text-[12px] text-foreground font-code truncate flex-1 min-w-0">
									{wh.url}
								</code>
								<span className="text-[11.5px] font-medium text-muted-foreground shrink-0">
									{wh.events.join(", ")}
								</span>
								<button type="button" onClick={() => handleDelete(wh.id)} className={REMOVE}>
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
						className={`${FIELD} flex-1 font-code`}
					/>
					<Button
						variant="secondary"
						size="sm"
						onClick={handleAdd}
						disabled={!newUrl.trim() || adding}
					>
						<Plus />
						Add
					</Button>
				</div>
			</Panel>
		</section>
	);
}
