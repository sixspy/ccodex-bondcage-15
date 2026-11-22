export const forfeitViewTemplate = `
<section class="panel">
  <h2>罚没册</h2>
  <p class="hint">
    仅核验违约的笼可罚没。违约出金门闸（纪要 {{ gateMeta.locked_at || '2026-11-22' }} 锁死 ·
    {{ gateMeta.basis || '甲路径·状态门闸拒写零增' }}）：违约态只允许罚没方向出金；
    部分罚没后可继续罚尾款，直到出清；同一笼代已有拨付则禁止罚没。
  </p>
  <div class="grid-2">
    <div>
      <div class="form-row">
        <div>
          <label>违约态笼</label>
          <select v-model.number="forfeitForm.cage_id">
            <option :value="0">请选择</option>
            <option v-for="c in forfeitableCages" :key="c.id" :value="c.id">
              {{ c.cage_code }} · 可用 {{ fmt(c.available) }}
            </option>
          </select>
        </div>
        <div>
          <label>金额（空=全额）</label>
          <input type="number" v-model.number="forfeitForm.amount" min="0" step="1000" placeholder="全额"/>
        </div>
        <div style="grid-column:1/-1">
          <label>原因</label>
          <input v-model="forfeitForm.reason"/>
        </div>
      </div>
      <div class="actions">
        <button class="danger" @click="doForfeit">执行罚没</button>
      </div>
      <div v-if="forfeitForm.cage_id" class="gate-note">
        <span class="badge fail">门闸限定罚没方向</span>
        {{ (gateOf(forfeitForm.cage_id) || {}).reason || '违约态：只允许罚没出金' }}
      </div>
      <div class="gate-block">
        <h3>违约笼出金方向（五页同源）</h3>
        <table>
          <thead><tr><th>笼</th><th>状态</th><th>可用</th><th>出金方向</th></tr></thead>
          <tbody>
            <tr v-for="g in breachGates" :key="'fg-'+g.cage_id">
              <td>{{ g.cage_code }}</td>
              <td><span class="badge fail">{{ g.status }}</span></td>
              <td>{{ fmt(g.available) }}</td>
              <td><span class="badge fail">{{ g.outflow }}</span></td>
            </tr>
            <tr v-if="!breachGates.length">
              <td colspan="4" class="hint">暂无违约笼</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div>
      <table>
        <thead>
          <tr><th>凭证</th><th>笼</th><th>金额</th><th>原因</th><th>笼代</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="f in forfeits" :key="f.id">
            <td>{{ f.forfeit_ref }}</td>
            <td>{{ f.cage_code }}</td>
            <td>{{ fmt(f.amount) }}</td>
            <td>{{ f.reason }}</td>
            <td>{{ f.cage_generation }}</td>
            <td>{{ f.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</section>
`;
