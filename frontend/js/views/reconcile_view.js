export const reconcileViewTemplate = `
<section class="panel">
  <h2>对账互证</h2>
  <p class="hint">笼口径：可用 + 已拨付 + 已罚没 = 笼总额（同笼代）。当事人口径：账户冻结 = 活笼可用合计。</p>
  <p class="hint">
    违约出金门闸（纪要 {{ gateMeta.locked_at || '2026-11-22' }} 锁死 · {{ gateMeta.basis || '甲路径·状态门闸拒写零增' }}）：
    对账页与解笼/罚没/核验/审计页共用同一判定；违约笼只准罚没方向出金，违者记为门闸偏航。
  </p>
  <div class="actions">
    <button @click="loadReconcile">刷新对账</button>
    <button class="secondary" @click="loadProof">当事人互证</button>
  </div>
  <div class="form-row" style="max-width:360px">
    <div>
      <label>当事人键（互证）</label>
      <input v-model="proofParty" list="party-list-recon"/>
      <datalist id="party-list-recon">
        <option v-for="b in bonds" :key="b.party_key" :value="b.party_key"/>
      </datalist>
    </div>
  </div>
  <div v-if="recon.summary" class="hint">
    合计 {{ recon.summary.total }} · 平衡 {{ recon.summary.balanced }} · 失衡 {{ recon.summary.unbalanced }}
  </div>
  <table>
    <thead>
      <tr>
        <th>笼</th><th>代</th><th>状态</th><th>门闸</th><th>总额</th><th>可用</th>
        <th>拨付</th><th>罚没</th><th>合计</th><th>平衡</th><th>缺口</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="i in (recon.items||[])" :key="i.cage_id">
        <td>{{ i.cage_code }}</td>
        <td>{{ i.generation }}</td>
        <td>{{ i.status }}</td>
        <td>
          <span class="badge" :class="(gateOf(i.cage_id)||{}).breach?'fail':'pass'">
            {{ (gateOf(i.cage_id)||{}).outflow || '—' }}
          </span>
        </td>
        <td>{{ fmt(i.amount) }}</td>
        <td>{{ fmt(i.available) }}</td>
        <td>{{ fmt(i.released) }}</td>
        <td>{{ fmt(i.forfeited) }}</td>
        <td>{{ fmt(i.accounted) }}</td>
        <td>
          <span class="badge" :class="i.balanced?'pass':'fail'">{{ i.balanced ? '是' : '否' }}</span>
        </td>
        <td>{{ fmt(i.gap) }}</td>
      </tr>
    </tbody>
  </table>
  <div v-if="partyProof" style="margin-top:14px">
    <h3>当事人互证 · {{ partyProof.party_key }}</h3>
    <div class="proof-box">{{ JSON.stringify(partyProof.proof, null, 2) }}
账户冻结 {{ fmt(partyProof.account.frozen) }}
活笼可用 {{ fmt(partyProof.live_cage_available) }}
匹配 {{ partyProof.frozen_matches_live }}
拨付合计 {{ fmt(partyProof.released_total) }}
罚没合计 {{ fmt(partyProof.forfeited_total) }}</div>
  </div>
</section>
`;
