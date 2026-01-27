/**
 * PairGroupManager component - modal for managing custom pair groups.
 */

import { useState, useEffect } from 'react'
import type { PairGroup } from '../../api/runs'

interface PairGroupManagerProps {
  groups: PairGroup[]
  availablePairs: string[]
  onSave: (groups: PairGroup[]) => void
  onClose: () => void
}

export function PairGroupManager({
  groups,
  availablePairs,
  onSave,
  onClose,
}: PairGroupManagerProps) {
  const [editableGroups, setEditableGroups] = useState<PairGroup[]>([])
  const [editingGroupIndex, setEditingGroupIndex] = useState<number | null>(null)
  const [newGroupName, setNewGroupName] = useState('')
  const [selectedPairs, setSelectedPairs] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setEditableGroups([...groups])
  }, [groups])

  // Get pairs already assigned to other groups (excluding the one being edited)
  const getAssignedPairs = (): Set<string> => {
    const assigned = new Set<string>()
    editableGroups.forEach((group, idx) => {
      if (idx !== editingGroupIndex) {
        group.pairs.forEach((pair) => assigned.add(pair))
      }
    })
    return assigned
  }

  const handleAddGroup = () => {
    setEditingGroupIndex(editableGroups.length)
    setNewGroupName('')
    setSelectedPairs(new Set())
    setError(null)
  }

  const handleEditGroup = (index: number) => {
    const group = editableGroups[index]
    setEditingGroupIndex(index)
    setNewGroupName(group.name)
    setSelectedPairs(new Set(group.pairs))
    setError(null)
  }

  const handleDeleteGroup = (index: number) => {
    setEditableGroups((prev) => prev.filter((_, i) => i !== index))
    if (editingGroupIndex === index) {
      setEditingGroupIndex(null)
    }
  }

  const handlePairToggle = (pair: string) => {
    setSelectedPairs((prev) => {
      const next = new Set(prev)
      if (next.has(pair)) {
        next.delete(pair)
      } else {
        next.add(pair)
      }
      return next
    })
  }

  const handleSaveGroup = () => {
    // Validate group name
    const trimmedName = newGroupName.trim()
    if (!trimmedName) {
      setError('Group name is required')
      return
    }
    if (trimmedName.toUpperCase() === 'ALL') {
      setError("'ALL' is reserved and cannot be used as a group name")
      return
    }

    // Check for duplicate name (excluding current group being edited)
    const nameExists = editableGroups.some(
      (g, idx) => idx !== editingGroupIndex && g.name.toLowerCase() === trimmedName.toLowerCase()
    )
    if (nameExists) {
      setError('A group with this name already exists')
      return
    }

    // Validate pairs selection
    if (selectedPairs.size === 0) {
      setError('Select at least one pair for the group')
      return
    }

    const newGroup: PairGroup = {
      name: trimmedName,
      pairs: Array.from(selectedPairs).sort(),
    }

    if (editingGroupIndex !== null && editingGroupIndex < editableGroups.length) {
      // Update existing group
      setEditableGroups((prev) =>
        prev.map((g, idx) => (idx === editingGroupIndex ? newGroup : g))
      )
    } else {
      // Add new group
      setEditableGroups((prev) => [...prev, newGroup])
    }

    setEditingGroupIndex(null)
    setNewGroupName('')
    setSelectedPairs(new Set())
    setError(null)
  }

  const handleCancelEdit = () => {
    setEditingGroupIndex(null)
    setNewGroupName('')
    setSelectedPairs(new Set())
    setError(null)
  }

  const handleSaveAll = () => {
    onSave(editableGroups)
    onClose()
  }

  const assignedPairs = getAssignedPairs()

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content pair-group-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Manage Pair Groups</h3>
          <button className="modal-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="modal-body">
          {/* Existing Groups */}
          <div className="groups-list">
            <div className="groups-header">
              <h4>Groups ({editableGroups.length})</h4>
              <button
                className="btn btn-sm btn-secondary"
                onClick={handleAddGroup}
                disabled={editingGroupIndex !== null}
              >
                + Add Group
              </button>
            </div>

            {editableGroups.length === 0 && editingGroupIndex === null && (
              <p className="empty-message">
                No custom groups defined. Add a group to categorize pairs.
              </p>
            )}

            {editableGroups.map((group, index) => (
              <div
                key={index}
                className={`group-item ${editingGroupIndex === index ? 'editing' : ''}`}
              >
                <div className="group-info">
                  <span className="group-name">{group.name}</span>
                  <span className="group-pairs">{group.pairs.join(', ')}</span>
                </div>
                <div className="group-actions">
                  <button
                    className="btn btn-sm btn-ghost"
                    onClick={() => handleEditGroup(index)}
                    disabled={editingGroupIndex !== null}
                  >
                    Edit
                  </button>
                  <button
                    className="btn btn-sm btn-ghost btn-danger-text"
                    onClick={() => handleDeleteGroup(index)}
                    disabled={editingGroupIndex !== null}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Edit/Add Form */}
          {editingGroupIndex !== null && (
            <div className="group-edit-form">
              <h4>
                {editingGroupIndex < editableGroups.length ? 'Edit Group' : 'New Group'}
              </h4>

              {error && <div className="form-error">{error}</div>}

              <div className="form-field">
                <label>Group Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="e.g., G3, Scandies, EM"
                />
              </div>

              <div className="form-field">
                <label>Select Pairs</label>
                <div className="pair-selection-grid">
                  {availablePairs.map((pair) => {
                    const isAssignedToOther = assignedPairs.has(pair)
                    return (
                      <label
                        key={pair}
                        className={`pair-checkbox ${isAssignedToOther ? 'disabled' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedPairs.has(pair)}
                          onChange={() => handlePairToggle(pair)}
                          disabled={isAssignedToOther}
                        />
                        <span>{pair}</span>
                        {isAssignedToOther && (
                          <span className="assigned-badge">assigned</span>
                        )}
                      </label>
                    )
                  })}
                </div>
                <p className="form-hint">
                  Selected: {selectedPairs.size} pair(s)
                  {assignedPairs.size > 0 && (
                    <> (grayed pairs are in other groups)</>
                  )}
                </p>
              </div>

              <div className="form-edit-actions">
                <button className="btn btn-secondary" onClick={handleCancelEdit}>
                  Cancel
                </button>
                <button className="btn btn-primary" onClick={handleSaveGroup}>
                  {editingGroupIndex < editableGroups.length ? 'Update' : 'Add'} Group
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSaveAll}
            disabled={editingGroupIndex !== null}
          >
            Save Groups
          </button>
        </div>
      </div>
    </div>
  )
}
