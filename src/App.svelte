<script lang="ts">
  import { onMount } from "svelte";

  let status = $state("connecting");
  let player = $state<string | null>(null);
  let games = $state<number>(0);
  let error = $state<string | null>(null);

  const API_BASE = "http://localhost:8420/api/v1";

  onMount(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      player = data.player_id;
      games = data.cached_games;
      status = "connected";
    } catch (e: any) {
      status = "error";
      error = e.message;
    }
  });
</script>

<main class="flex items-center justify-center h-screen">
  <div class="text-center">
    <h1 class="text-4xl font-bold text-white mb-2">Verdict</h1>
    <p class="text-slate-400 mb-8">League of Legends Diagnostic Tool</p>

    {#if status === "connecting"}
      <div class="flex items-center justify-center gap-2 text-slate-400">
        <svg class="animate-spin h-5 w-5" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Connecting to server...
      </div>
    {:else if status === "connected"}
      <div class="bg-slate-800 rounded-lg p-6 shadow-lg border border-slate-700">
        <div class="flex items-center gap-2 mb-4">
          <div class="h-3 w-3 rounded-full bg-green-500"></div>
          <span class="text-green-400 font-medium">Server Connected</span>
        </div>
        {#if player}
          <p class="text-slate-300">Player: <span class="text-white font-semibold">{player}</span></p>
        {/if}
        <p class="text-slate-300">Cached games: <span class="text-white font-semibold">{games}</span></p>
      </div>
    {:else}
      <div class="bg-red-900/30 rounded-lg p-6 border border-red-800">
        <p class="text-red-400 font-medium">Connection Failed</p>
        <p class="text-red-300 text-sm mt-2">{error}</p>
        <p class="text-slate-500 text-sm mt-2">Make sure the server is running on port 8420</p>
      </div>
    {/if}
  </div>
</main>