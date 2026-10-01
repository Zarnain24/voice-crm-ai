import { useState } from 'react'
import { api } from '../api'

const EMPTY = { name: '', title: '', company: '', email: '', phone: '', opportunity_title: '', opportunity_value: '' }

export function NewLeadDialog({ onClose, onError }) {
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      // Send only filled-in fields; the API validates types and lengths.
      const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v.trim() !== ''))
      if (payload.opportunity_value) payload.opportunity_value = Number(payload.opportunity_value)
      await api.createContact(payload)
      onClose()
    } catch (err) {
      onError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="overlay center" onClick={onClose}>
      <form className="dialog" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2>New lead</h2>
        <div className="grid-2">
          <label>
            Name *<input required maxLength={120} value={form.name} onChange={set('name')} autoFocus />
          </label>
          <label>
            Job title<input maxLength={120} value={form.title} onChange={set('title')} placeholder="e.g. Billing Manager" />
          </label>
        </div>
        <label>
          Utility / company<input maxLength={120} value={form.company} onChange={set('company')} />
        </label>
        <div className="grid-2">
          <label>
            Email<input type="email" value={form.email} onChange={set('email')} />
          </label>
          <label>
            Phone<input maxLength={40} value={form.phone} onChange={set('phone')} />
          </label>
        </div>
        <div className="grid-2">
          <label>
            Deal<input maxLength={160} value={form.opportunity_title} onChange={set('opportunity_title')} placeholder="e.g. CIS Infinity billing migration" />
          </label>
          <label>
            Value ($)<input type="number" min={0} value={form.opportunity_value} onChange={set('opportunity_value')} />
          </label>
        </div>
        <p className="hint">Automation: a lead with a deal gets an "Initial outreach" task due today.</p>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" disabled={saving}>
            {saving ? 'Saving…' : 'Create lead'}
          </button>
        </div>
      </form>
    </div>
  )
}
