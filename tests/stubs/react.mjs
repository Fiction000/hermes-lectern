export const useEffect = () => {};
export const useMemo = fn => fn();
export const useRef = value => ({ current: value });
export const useState = value => [value, () => {}];
