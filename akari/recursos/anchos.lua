-- Reparte el ancho de las columnas de cada tabla según cuánto texto tienen
-- (pandoc las deja iguales o según los guiones del separador, y salen aplastadas).
local function largo(celda)
  return utf8.len(pandoc.utils.stringify(celda.contents)) or 0
end

local function palabraMasLarga(celda)
  local m = 0
  for p in pandoc.utils.stringify(celda.contents):gmatch("%S+") do m = math.max(m, utf8.len(p) or #p) end
  return m
end

function Table(t)
  local n = #t.colspecs
  if n == 0 then return nil end
  local pesos = {}
  for i = 1, n do pesos[i] = 4 end
  local function medir(filas)
    for _, fila in ipairs(filas) do
      for i, celda in ipairs(fila.cells) do
        if i <= n then pesos[i] = math.max(pesos[i], math.sqrt(largo(celda)) * 4, math.min(largo(celda), 12), palabraMasLarga(celda) * 1.2) end
      end
    end
  end
  medir(t.head.rows)
  for _, cuerpo in ipairs(t.bodies) do medir(cuerpo.body) end
  local total = 0
  for i = 1, n do total = total + pesos[i] end
  for i = 1, n do t.colspecs[i][2] = pesos[i] / total end
  return t
end
