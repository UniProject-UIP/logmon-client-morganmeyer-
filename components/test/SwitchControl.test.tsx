import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SwitchControl } from "../SwitchControl";

describe("SwitchControl", () => {
  it("refleja checked=false con aria-checked", () => {
    render(<SwitchControl checked={false} onChange={vi.fn()} />);

    const boton = screen.getByRole("switch");
    expect(boton).toHaveAttribute("aria-checked", "false");
  });

  it("refleja checked=true con aria-checked", () => {
    render(<SwitchControl checked={true} onChange={vi.fn()} />);

    const boton = screen.getByRole("switch");
    expect(boton).toHaveAttribute("aria-checked", "true");
  });

  it("llama a onChange con el valor invertido al hacer click", async () => {
    const usuario = userEvent.setup();
    const alCambiar = vi.fn();
    render(<SwitchControl checked={false} onChange={alCambiar} />);

    await usuario.click(screen.getByRole("switch"));

    expect(alCambiar).toHaveBeenCalledTimes(1);
    expect(alCambiar).toHaveBeenCalledWith(true);
  });

  it("togglea de true a false", async () => {
    const usuario = userEvent.setup();
    const alCambiar = vi.fn();
    render(<SwitchControl checked={true} onChange={alCambiar} />);

    await usuario.click(screen.getByRole("switch"));

    expect(alCambiar).toHaveBeenCalledWith(false);
  });

  it("no llama a onChange si está disabled", async () => {
    const usuario = userEvent.setup();
    const alCambiar = vi.fn();
    render(<SwitchControl checked={false} onChange={alCambiar} disabled />);

    await usuario.click(screen.getByRole("switch"));

    expect(alCambiar).not.toHaveBeenCalled();
  });

  it("el botón queda disabled en el DOM", () => {
    render(<SwitchControl checked={false} onChange={vi.fn()} disabled />);

    expect(screen.getByRole("switch")).toBeDisabled();
  });

  it("togglea con la tecla Enter", async () => {
    const usuario = userEvent.setup();
    const alCambiar = vi.fn();
    render(<SwitchControl checked={false} onChange={alCambiar} />);

    screen.getByRole("switch").focus();
    await usuario.keyboard("{Enter}");

    expect(alCambiar).toHaveBeenCalledWith(true);
  });

  it("togglea con la tecla espacio", async () => {
    const usuario = userEvent.setup();
    const alCambiar = vi.fn();
    render(<SwitchControl checked={false} onChange={alCambiar} />);

    screen.getByRole("switch").focus();
    await usuario.keyboard(" ");

    expect(alCambiar).toHaveBeenCalledWith(true);
  });

  it("no togglea con teclado si está disabled", async () => {
    const usuario = userEvent.setup();
    const alCambiar = vi.fn();
    render(<SwitchControl checked={false} onChange={alCambiar} disabled />);

    screen.getByRole("switch").focus();
    await usuario.keyboard("{Enter}");

    expect(alCambiar).not.toHaveBeenCalled();
  });

  it("muestra el label cuando se pasa", () => {
    render(
      <SwitchControl checked={false} onChange={vi.fn()} label="Conexión activa" />
    );

    expect(screen.getByText("Conexión activa")).toBeInTheDocument();
  });

  it("no renderiza texto de label cuando no se pasa", () => {
    const { container } = render(
      <SwitchControl checked={false} onChange={vi.fn()} />
    );

    expect(container.querySelector(".switch-control__label")).toBeNull();
  });

  it("asocia el id al botón para poder referenciarlo desde un label externo", () => {
    render(<SwitchControl id="activa" checked={false} onChange={vi.fn()} />);

    expect(screen.getByRole("switch")).toHaveAttribute("id", "activa");
  });
});