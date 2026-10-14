sub init()
    m.list = m.top.FindNode("list")
    m.list.ObserveField("rowItemFocused", "onFocused")
    m.list.ObserveField("rowItemSelected", "onSelected")
end sub

function itemAt(pair as object) as dynamic
    if m.list.content = invalid or pair.Count() < 2 then return invalid
    row = m.list.content.GetChild(pair[0])
    if row = invalid then return invalid
    return row.GetChild(pair[1])
end function

sub onFocused()
    m.top.focusedItem = itemAt(m.list.rowItemFocused)
end sub

sub onSelected()
    item = itemAt(m.list.rowItemSelected)
    if item = invalid then return
    m.top.selectedItem = item
    ' A mutable content node is data, never a selection event.
    m.top.selectionRequested++
end sub

sub focusList()
    m.list.SetFocus(true)
end sub

sub jumpToRow(index as integer)
    m.list.jumpToRowItem = [index, 0]
    m.list.SetFocus(true)
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    ' Only an unconsumed Up from the top boundary leaves the list.
    if key = "up"
        pair = m.list.rowItemFocused
        if pair.Count() < 2 then return false
        if pair[0] = 0
            m.top.exitUp++
            return true
        end if
    end if
    return false
end function
