/**
 * HedgingRuleBuilder component - dynamic table for configuring hedging rules.
 *
 * EXTENSIBILITY: To add a new action type:
 * 1. Add the new interface to runs.ts (ActionParams union)
 * 2. Add the action to ACTION_OPTIONS below
 * 3. Add parameter inputs in renderActionParams()
 * 4. Add default params in getDefaultActionParams()
 */

import { useState } from 'react'
import type {
  HedgingRule,
  HedgingRuleSet,
  PairGroup,
  AmountType,
  ActionParams,
  NoHedgeParams,
  HedgeToTargetParams,
  HedgePercentageParams,
} from '../../api/runs'
import { PairGroupManager } from './PairGroupManager'

interface HedgingRuleBuilderProps {
  ruleSet: HedgingRuleSet
  availablePairs: string[]
  onChange: (ruleSet: HedgingRuleSet) => void
}

// Action type options for dropdown
const ACTION_OPTIONS: { value: ActionParams['action_type']; label: string; description: string }[] = [
  {
    value: 'no_hedge',
    label: 'No Hedge',
    description: 'Do not hedge positions in this range',
  },
  {
    value: 'hedge_to_target',
    label: 'Hedge to Target',
    description: 'Hedge down to a percentage of the From Amount',
  },
  {
    value: 'hedge_percentage',
    label: 'Hedge Percentage',
    description: 'Hedge a percentage of the current position',
  },
]

// Get default action parameters for a given action type
function getDefaultActionParams(actionType: ActionParams['action_type']): ActionParams {
  switch (actionType) {
    case 'no_hedge':
      return { action_type: 'no_hedge' } as NoHedgeParams
    case 'hedge_to_target':
      return { action_type: 'hedge_to_target', target_percentage: 0.5 } as HedgeToTargetParams
    case 'hedge_percentage':
      return { action_type: 'hedge_percentage', hedge_percentage: 1.0 } as HedgePercentageParams
    default:
      return { action_type: 'no_hedge' } as NoHedgeParams
  }
}

// Create a default rule
function createDefaultRule(): HedgingRule {
  return {
    pair_or_group: 'ALL',
    amount_type: 'absolute',
    from_amount: 0,
    to_amount: Infinity,
    action: { action_type: 'no_hedge' },
  }
}

export function HedgingRuleBuilder({
  ruleSet,
  availablePairs,
  onChange,
}: HedgingRuleBuilderProps) {
  const [showGroupManager, setShowGroupManager] = useState(false)
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null)

  // Build pair/group options for dropdown
  const getPairGroupOptions = (): { value: string; label: string; type: 'pair' | 'group' | 'all' }[] => {
    const options: { value: string; label: string; type: 'pair' | 'group' | 'all' }[] = [
      { value: 'ALL', label: 'ALL (catch-all)', type: 'all' },
    ]

    // Add groups
    ruleSet.groups.forEach((group) => {
      options.push({
        value: group.name,
        label: `${group.name} (group: ${group.pairs.length} pairs)`,
        type: 'group',
      })
    })

    // Add individual pairs
    availablePairs.forEach((pair) => {
      options.push({ value: pair, label: pair, type: 'pair' })
    })

    return options
  }

  const handleAddRule = () => {
    const newRules = [...ruleSet.rules, createDefaultRule()]
    onChange({ ...ruleSet, rules: newRules })
  }

  const handleDeleteRule = (index: number) => {
    const newRules = ruleSet.rules.filter((_, i) => i !== index)
    // Ensure at least one rule exists
    if (newRules.length === 0) {
      newRules.push(createDefaultRule())
    }
    onChange({ ...ruleSet, rules: newRules })
  }

  const handleRuleChange = (index: number, field: keyof HedgingRule, value: unknown) => {
    const newRules = ruleSet.rules.map((rule, i) => {
      if (i !== index) return rule
      return { ...rule, [field]: value }
    })
    onChange({ ...ruleSet, rules: newRules })
  }

  const handleActionTypeChange = (index: number, actionType: ActionParams['action_type']) => {
    const newAction = getDefaultActionParams(actionType)
    handleRuleChange(index, 'action', newAction)
  }

  const handleActionParamChange = (index: number, param: string, value: number) => {
    const rule = ruleSet.rules[index]
    const newAction = { ...rule.action, [param]: value } as ActionParams
    handleRuleChange(index, 'action', newAction)
  }

  const handleGroupsChange = (groups: PairGroup[]) => {
    onChange({ ...ruleSet, groups })
  }

  // Drag and drop handlers
  const handleDragStart = (index: number) => {
    setDraggedIndex(index)
  }

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault()
    if (draggedIndex === null || draggedIndex === index) return
  }

  const handleDrop = (index: number) => {
    if (draggedIndex === null || draggedIndex === index) return

    const newRules = [...ruleSet.rules]
    const [draggedRule] = newRules.splice(draggedIndex, 1)
    newRules.splice(index, 0, draggedRule)
    onChange({ ...ruleSet, rules: newRules })
    setDraggedIndex(null)
  }

  const handleDragEnd = () => {
    setDraggedIndex(null)
  }

  // Format to_amount for display (handle Infinity)
  const formatAmount = (value: number): string => {
    if (!isFinite(value)) return 'inf'
    return value.toString()
  }

  // Parse amount input (handle 'inf')
  const parseAmount = (value: string): number => {
    if (value.toLowerCase() === 'inf' || value === '') return Infinity
    const num = parseFloat(value)
    return isNaN(num) ? 0 : num
  }

  const pairGroupOptions = getPairGroupOptions()

  return (
    <div className="hedging-rule-builder">
      {/* Group Management */}
      <div className="rule-builder-header">
        <div className="header-info">
          <h4>Hedging Rules</h4>
          <p className="form-hint">
            Rules are matched in order: Specific pair &gt; Group &gt; ALL. First match wins.
          </p>
        </div>
        <button
          className="btn btn-sm btn-secondary"
          onClick={() => setShowGroupManager(true)}
        >
          Manage Groups ({ruleSet.groups.length})
        </button>
      </div>

      {/* Groups Summary */}
      {ruleSet.groups.length > 0 && (
        <div className="groups-summary">
          {ruleSet.groups.map((group) => (
            <div key={group.name} className="group-badge">
              <span className="group-badge-name">{group.name}</span>
              <span className="group-badge-pairs">{group.pairs.join(', ')}</span>
            </div>
          ))}
        </div>
      )}

      {/* Rules Table */}
      <div className="rules-table">
        <div className="rules-table-header">
          <span className="col-drag"></span>
          <span className="col-target">Target</span>
          <span className="col-type">Amount Type</span>
          <span className="col-from">From</span>
          <span className="col-to">To</span>
          <span className="col-action">Action</span>
          <span className="col-params">Parameters</span>
          <span className="col-delete"></span>
        </div>

        {ruleSet.rules.map((rule, index) => (
          <div
            key={index}
            className={`rules-table-row ${draggedIndex === index ? 'dragging' : ''}`}
            draggable
            onDragStart={() => handleDragStart(index)}
            onDragOver={(e) => handleDragOver(e, index)}
            onDrop={() => handleDrop(index)}
            onDragEnd={handleDragEnd}
          >
            <span className="col-drag drag-handle" title="Drag to reorder">
              &#8942;&#8942;
            </span>

            <span className="col-target">
              <select
                className="form-select compact"
                value={rule.pair_or_group}
                onChange={(e) => handleRuleChange(index, 'pair_or_group', e.target.value)}
              >
                {pairGroupOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </span>

            <span className="col-type">
              <select
                className="form-select compact"
                value={rule.amount_type}
                onChange={(e) =>
                  handleRuleChange(index, 'amount_type', e.target.value as AmountType)
                }
              >
                <option value="absolute">Absolute</option>
                <option value="signed">Signed</option>
              </select>
            </span>

            <span className="col-from">
              <input
                type="number"
                className="form-input compact"
                value={rule.from_amount}
                onChange={(e) =>
                  handleRuleChange(index, 'from_amount', parseFloat(e.target.value) || 0)
                }
                step={100}
              />
            </span>

            <span className="col-to">
              <input
                type="text"
                className="form-input compact"
                value={formatAmount(rule.to_amount)}
                onChange={(e) => handleRuleChange(index, 'to_amount', parseAmount(e.target.value))}
                placeholder="inf"
              />
            </span>

            <span className="col-action">
              <select
                className="form-select compact"
                value={rule.action.action_type}
                onChange={(e) =>
                  handleActionTypeChange(index, e.target.value as ActionParams['action_type'])
                }
              >
                {ACTION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </span>

            <span className="col-params">
              {renderActionParams(rule.action, index, handleActionParamChange)}
            </span>

            <span className="col-delete">
              <button
                className="btn btn-sm btn-ghost btn-danger-text"
                onClick={() => handleDeleteRule(index)}
                title="Delete rule"
                disabled={ruleSet.rules.length === 1}
              >
                &times;
              </button>
            </span>
          </div>
        ))}
      </div>

      {/* Add Rule Button */}
      <div className="rules-actions">
        <button className="btn btn-secondary" onClick={handleAddRule}>
          + Add Rule
        </button>
      </div>

      {/* Priority Explanation */}
      <div className="priority-explanation">
        <h5>Priority Order</h5>
        <ol>
          <li><strong>Specific Pair</strong> - Rules targeting a specific pair (e.g., EURUSD)</li>
          <li><strong>Group</strong> - Rules targeting a custom group (e.g., G3)</li>
          <li><strong>ALL</strong> - Catch-all rules for any pair not matched above</li>
        </ol>
        <p>Within the same priority level, the first matching rule wins.</p>
      </div>

      {/* Group Manager Modal */}
      {showGroupManager && (
        <PairGroupManager
          groups={ruleSet.groups}
          availablePairs={availablePairs}
          onSave={handleGroupsChange}
          onClose={() => setShowGroupManager(false)}
        />
      )}
    </div>
  )
}

// Render action-specific parameters
function renderActionParams(
  action: ActionParams,
  index: number,
  onChange: (index: number, param: string, value: number) => void
): React.ReactNode {
  switch (action.action_type) {
    case 'no_hedge':
      return <span className="param-none">-</span>

    case 'hedge_to_target':
      return (
        <div className="param-input">
          <label>Target:</label>
          <input
            type="number"
            className="form-input compact"
            value={(action as HedgeToTargetParams).target_percentage * 100}
            onChange={(e) =>
              onChange(index, 'target_percentage', parseFloat(e.target.value) / 100 || 0)
            }
            min={0}
            max={100}
            step={5}
          />
          <span className="param-unit">%</span>
        </div>
      )

    case 'hedge_percentage':
      return (
        <div className="param-input">
          <label>Hedge:</label>
          <input
            type="number"
            className="form-input compact"
            value={(action as HedgePercentageParams).hedge_percentage * 100}
            onChange={(e) =>
              onChange(index, 'hedge_percentage', parseFloat(e.target.value) / 100 || 0)
            }
            min={0}
            max={100}
            step={5}
          />
          <span className="param-unit">%</span>
        </div>
      )

    default:
      return <span className="param-none">-</span>
  }
}
