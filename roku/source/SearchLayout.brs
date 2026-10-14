' Fit native keyboard variants inside the space above the separate action row.
function SearchKeyboardPlacement(bounds as dynamic) as dynamic
    if bounds = invalid then return invalid
    width = MediaNumber(bounds.width)
    height = MediaNumber(bounds.height)
    if width <= 0 or height <= 0 then return invalid
    amount = 0.82
    if width * amount > 448 then amount = 448 / width
    if height * amount > 384 then amount = 384 / height
    return {scale:amount, translation:[-MediaNumber(bounds.x) * amount, -MediaNumber(bounds.y) * amount]}
end function
